import { useEffect, useRef, useState } from 'react'
import maplibregl from 'maplibre-gl'
import { fetchPointsMobilite, fetchPointsConnectivite } from '../api/index'

// Associe chaque indicateur à sa fonction de fetch MongoDB
const POINTS_FETCHERS = {
  mobilite:     fetchPointsMobilite,
  connectivite: fetchPointsConnectivite,
}

// URL GeoJSON Open Data Paris — contours officiels des 20 arrondissements
const PARIS_GEOJSON_URL = 'https://opendata.paris.fr/api/explore/v2.1/catalog/datasets/arrondissements/exports/geojson?lang=fr'

// Modes de transport affichés dans le popup mobilité (key = colonne Gold PostgreSQL)
const MODES = [
  { key: 'nb_arrets_bus',           label: 'Bus',           icon: '🚌' },
  { key: 'nb_arrets_metro',         label: 'Métro',         icon: '🚇' },
  { key: 'nb_arrets_rer',           label: 'RER',           icon: '🚆' },
  { key: 'nb_arrets_tram',          label: 'Tram',          icon: '🚊' },
  { key: 'nb_arrets_train',         label: 'Train',         icon: '🚂' },
  { key: 'nb_arrets_train_regional',label: 'Régional',      icon: '🚄' },
  { key: 'nb_arrets_funiculaire',   label: 'Funiculaire',   icon: '🚡' },
]

// Génère le HTML du popup au survol d'un arrondissement
function buildPopupHTML(arrNum, cp, data, indicateurId) {
  if (!data) return `<div class="popup-cp">Paris ${arrNum}e</div><div class="popup-postal">${cp}</div>`
  const score = data.score_mobilite_100 ?? data.score_connectivite_100 ?? '—'
  const header = `
    <div class="popup-cp">Paris ${arrNum}e <span class="popup-postal-inline">${cp}</span></div>
    <div class="popup-score">${score}<span>/100</span></div>
    <div class="popup-rang">Rang #${data.rang} · ${data.categorie}</div>
    <div class="popup-divider"></div>
  `
  if (indicateurId === 'mobilite') {
    const modesHTML = MODES
      .filter(m => data[m.key] > 0)
      .map(m => `
        <div class="popup-stat">
          <span class="popup-stat-val">${parseInt(data[m.key])}</span>
          <span class="popup-stat-lbl">${m.label}</span>
        </div>
      `).join('')
    return header + `
      <div class="popup-section-title">Arrets par mode</div>
      <div class="popup-grid">${modesHTML}</div>
      <div class="popup-divider"></div>
      <div class="popup-section-title">Stationnement</div>
      <div class="popup-grid">
        <div class="popup-stat"><span class="popup-stat-val">${data.nb_bornes}</span><span class="popup-stat-lbl">Bornes taxi</span></div>
        <div class="popup-stat"><span class="popup-stat-val">${data.nb_places_gratuit}</span><span class="popup-stat-lbl">Gratuit</span></div>
        <div class="popup-stat"><span class="popup-stat-val">${data.nb_places_payant}</span><span class="popup-stat-lbl">Payant</span></div>
        <div class="popup-stat"><span class="popup-stat-val">${data.nb_places_2roues}</span><span class="popup-stat-lbl">2-roues</span></div>
        <div class="popup-stat"><span class="popup-stat-val">${data.nb_places_pmr}</span><span class="popup-stat-lbl">PMR</span></div>
        <div class="popup-stat"><span class="popup-stat-val">${data.nb_places_electrique}</span><span class="popup-stat-lbl">Elec.</span></div>
      </div>
    `
  }
  if (indicateurId === 'connectivite') {
    return header + `
      <div class="popup-section-title">Antennes</div>
      <div class="popup-grid">
        <div class="popup-stat"><span class="popup-stat-val">${data.nb_antennes ?? 0}</span><span class="popup-stat-lbl">Total</span></div>
        <div class="popup-stat"><span class="popup-stat-val">${data.nb_antennes_5g ?? 0}</span><span class="popup-stat-lbl">5G</span></div>
        <div class="popup-stat"><span class="popup-stat-val">${data.nb_antennes_4g ?? 0}</span><span class="popup-stat-lbl">4G</span></div>
      </div>
      <div class="popup-divider"></div>
      <div class="popup-section-title">Couverture</div>
      <div class="popup-grid">
        <div class="popup-stat"><span class="popup-stat-val">${data.taux_4g ?? 0}%</span><span class="popup-stat-lbl">4G</span></div>
        <div class="popup-stat"><span class="popup-stat-val">${data.taux_5g ?? 0}%</span><span class="popup-stat-lbl">5G</span></div>
        <div class="popup-stat popup-stat-full"><span class="popup-stat-val">${data.operateur_leader ?? '—'}</span><span class="popup-stat-lbl">Operateur leader</span></div>
      </div>
    `
  }
  return header
}

export default function MapView({ scores, scoreKey, activeColor, activeIndicateur, visibleTypes, selected, onSelect, is3D, loading }) {
  const mapContainer = useRef(null)
  const map          = useRef(null)
  const popup        = useRef(null)
  const markersByTypeId  = useRef({})
  const allPointsCache   = useRef({})
  const [mapReady, setMapReady] = useState(false)

  // Refs miroir — permettent aux callbacks MapLibre de lire les valeurs React à jour
  const visibleTypesRef = useRef(visibleTypes)
  useEffect(() => { visibleTypesRef.current = visibleTypes }, [visibleTypes])
  const activeIndicateurRef = useRef(activeIndicateur)
  useEffect(() => { activeIndicateurRef.current = activeIndicateur }, [activeIndicateur])

  // Supprime tous les markers de la carte
  const clearMarkers = () => {
    Object.values(markersByTypeId.current).flat().forEach(m => { try { m.remove() } catch (_) {} })
    markersByTypeId.current = {}
  }

  // Affiche les markers géolocalisés pour un arrondissement depuis le cache client
  const showMarkersForCP = (cp) => {
    clearMarkers()
    const ind = activeIndicateurRef.current
    if (!cp || !ind?.pointTypes) return
    const cacheKey = `${ind.id}_${cp}`
    const geojson = allPointsCache.current[cacheKey]
    if (!geojson?.features) return
    const filtered = geojson.features.filter(f =>
      String(f.properties?.code_postal) === String(cp)
    )
    ind.pointTypes.forEach(pointType => {
      const matchingFeatures = filtered.filter(f => {
        const props = f.properties
        if (props.type !== pointType.mongoType) return false
        if (pointType.modeFilter && props.mode_nom !== pointType.modeFilter) return false
        return true
      })
      if (matchingFeatures.length === 0) return
      const isVisible = visibleTypesRef.current.includes(pointType.id)
      markersByTypeId.current[pointType.id] = matchingFeatures.map(f => {
        const [lng, lat] = f.geometry.coordinates
        const el = document.createElement('div')
        el.style.cssText = `
          width: 10px; height: 10px; border-radius: 50%;
          background: ${pointType.color}; border: 1.5px solid #fff;
          display: ${isVisible ? 'block' : 'none'};
        `
        return new maplibregl.Marker({ element: el })
          .setLngLat([lng, lat])
          .addTo(map.current)
      })
    })
  }

  // Initialise la carte MapLibre avec fond OSM, layers 3D et events clic/survol
  useEffect(() => {
    if (map.current) return
    popup.current = new maplibregl.Popup({
      closeButton: false, closeOnClick: false,
      className: 'ude-popup', offset: 10, maxWidth: '300px',
    })
    map.current = new maplibregl.Map({
      container: mapContainer.current,
      style: {
        version: 8,
        glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
        sources: { osm: { type: 'raster', tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'], tileSize: 256 } },
        layers: [{ 
          id: 'osm-tiles', type: 'raster', source: 'osm',
          paint: { 
            'raster-opacity': ['interpolate', ['linear'], ['zoom'], 11, 0.15, 13, 0.6, 15, 1.0]
          } 
        }]
      },
      center: [2.3488, 48.8534], zoom: 11.5, pitch: 45, bearing: -15, antialias: true,
    })
    map.current.addControl(new maplibregl.NavigationControl(), 'top-right')
    map.current.on('load', () => {
      fetch(PARIS_GEOJSON_URL)
        .then(r => r.json())
        .then(geojson => {
          geojson.features = geojson.features.map(f => ({
            ...f,
            properties: {
              ...f.properties,
              code_postal: f.properties.c_ar ? `750${String(f.properties.c_ar).padStart(2, '0')}` : ''
            }
          }))
          map.current.addSource('arrondissements', { type: 'geojson', data: geojson })
          map.current.addLayer({ id: 'arrondissements-3d', type: 'fill-extrusion', source: 'arrondissements',
            paint: { 'fill-extrusion-color': '#00d4aa', 'fill-extrusion-height': 100, 'fill-extrusion-base': 0, 'fill-extrusion-opacity': 0.75 }
          })
          map.current.addLayer({ id: 'arrondissements-outline', type: 'line', source: 'arrondissements',
            paint: { 'line-color': '#0a0e1a', 'line-width': 1.5 }
          })
          map.current.addLayer({ id: 'arrondissements-labels', type: 'symbol', source: 'arrondissements',
            layout: {
              'text-field': ['get', 'code_postal'], 'text-font': ['Noto Sans Regular'], 'text-size': 11,
              'text-anchor': 'center', 'text-allow-overlap': true, 'text-ignore-placement': true,
              'text-pitch-alignment': 'map', 'text-rotation-alignment': 'map',
            },
            paint: { 'text-color': '#ffffff', 'text-halo-color': '#000000', 'text-halo-width': 2 }
          })
          // window utilisé car les callbacks MapLibre ne lisent pas le state React
          map.current.on('mousemove', 'arrondissements-3d', (e) => {
            const props  = e.features[0].properties
            const arrNum = props.c_ar
            const cp     = arrNum ? 75000 + parseInt(arrNum) : null
            const data = (window.__ude_scores || []).find(s => s.code_postal === cp)
            popup.current.setLngLat(e.lngLat).setHTML(buildPopupHTML(arrNum, cp, data, window.__ude_indicateurId)).addTo(map.current)
            map.current.getCanvas().style.cursor = 'pointer'
          })
          map.current.on('mouseleave', 'arrondissements-3d', () => { popup.current.remove(); map.current.getCanvas().style.cursor = '' })
          map.current.on('click', 'arrondissements-3d', (e) => {
            const cp = e.features[0].properties.c_ar ? 75000 + parseInt(e.features[0].properties.c_ar) : null
            onSelect(cp)
          })
          setMapReady(true)
        })
    })
    return () => { map.current?.remove(); map.current = null }
  }, [])

  // Synchronise les scores vers window pour les callbacks MapLibre
  useEffect(() => {
    window.__ude_scores       = scores
    window.__ude_scoreKey     = scoreKey
    window.__ude_indicateurId = activeIndicateur?.id
  }, [scores, scoreKey, activeIndicateur?.id])

  // Met à jour les couleurs et hauteurs 3D des arrondissements selon les scores
  useEffect(() => {
    if (!mapReady || !map.current || !scores.length || !scoreKey) return
    const colorExpr  = ['match', ['get', 'c_ar']]
    const heightExpr = ['match', ['get', 'c_ar']]
    const targetArrNum = selected ? selected - 75000 : null
    const darkColor = activeIndicateur?.darkColor ?? '#0d1117'
    scores.forEach(s => {
      const arrNum = s.code_postal - 75000  // ← calcul depuis code_postal
      const normalized = (s[scoreKey] ?? 0) / 100
      let baseColor = interpolateColor(darkColor, activeColor, normalized)
      if (targetArrNum !== null && arrNum !== targetArrNum) {
        baseColor = interpolateColor('#1a2634', baseColor, 0.3)
      }
      colorExpr.push(arrNum, baseColor)
      heightExpr.push(arrNum, is3D ? Math.round(200 + normalized * 1200) : 0)
    })
    colorExpr.push(darkColor); heightExpr.push(0)
    map.current.setPaintProperty('arrondissements-3d', 'fill-extrusion-color', colorExpr)
    map.current.setPaintProperty('arrondissements-3d', 'fill-extrusion-height', heightExpr)
    map.current.setPaintProperty('arrondissements-3d', 'fill-extrusion-opacity', is3D ? 0.75 : 0.85)
  }, [scores, scoreKey, activeColor, activeIndicateur?.darkColor, mapReady, is3D, selected])

  // Fetch les points MongoDB au clic et les met en cache par arrondissement
  useEffect(() => {
    clearMarkers()
    if (!mapReady || !activeIndicateur?.pointsEndpoint || !selected) return
    const cacheKey = `${activeIndicateur.id}_${selected}`
    const fetcher = POINTS_FETCHERS[activeIndicateur.id]
    if (!fetcher) return
    if (allPointsCache.current[cacheKey]) {
      showMarkersForCP(selected)
      return
    }
    fetcher(selected)
      .then(geojson => {
        allPointsCache.current[cacheKey] = geojson
        showMarkersForCP(selected)
      })
      .catch(console.error)
  }, [activeIndicateur?.id, mapReady, selected])

  // Affiche ou masque les markers selon les filtres du panneau latéral
  useEffect(() => {
    Object.entries(markersByTypeId.current).forEach(([typeId, markers]) => {
      const show = visibleTypes.includes(typeId)
      markers.forEach(m => { m.getElement().style.display = show ? 'block' : 'none' })
    })
  }, [visibleTypes])

  // Bascule entre vue 3D et vue plate avec animation
  useEffect(() => {
    if (!map.current) return
    map.current.easeTo({ pitch: is3D ? 45 : 0, bearing: is3D ? -15 : 0, duration: 600 })
  }, [is3D])

  return (
    <div className="map-container">
      {loading && <div className="loading-overlay"><span className="loading-dot" />Chargement...</div>}
      <div ref={mapContainer} style={{ width: '100%', height: '100%' }} />
    </div>
  )
}

// Interpolation linéaire entre deux couleurs hex selon un score normalisé (0 → 1)
function interpolateColor(hex1, hex2, t) {
  const r1=parseInt(hex1.slice(1,3),16),g1=parseInt(hex1.slice(3,5),16),b1=parseInt(hex1.slice(5,7),16)
  const r2=parseInt(hex2.slice(1,3),16),g2=parseInt(hex2.slice(3,5),16),b2=parseInt(hex2.slice(5,7),16)
  const r=Math.round(r1+(r2-r1)*t),g=Math.round(g1+(g2-g1)*t),b=Math.round(b1+(b2-b1)*t)
  return `#${r.toString(16).padStart(2,'0')}${g.toString(16).padStart(2,'0')}${b.toString(16).padStart(2,'0')}`
}
