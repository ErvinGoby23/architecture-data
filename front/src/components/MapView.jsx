import { useEffect, useRef, useState } from 'react'
import maplibregl from 'maplibre-gl'
import { fetchPointsMobilite, fetchPointsConnectivite, fetchPointsServices, fetchPointsLogement } from '../api/index'

// année courante partagée avec le wrapper logement (mise à jour par un effet)
let _currentYear = null

const POINTS_FETCHERS = {
  mobilite:     fetchPointsMobilite,
  connectivite: fetchPointsConnectivite,
  services:     fetchPointsServices,
  // logement : signature adaptée + année active + (les 2 types de points sont renvoyés)
  logement: ({ granularite, arrondissement, code_quartier }) =>
    fetchPointsLogement({
      arrondissement: granularite === 'quartier' ? null : arrondissement,
      code_quartier:  granularite === 'quartier' ? code_quartier : null,
      annee: _currentYear,
    }),
}

const ARRONDISSEMENTS_URL = 'https://opendata.paris.fr/api/explore/v2.1/catalog/datasets/arrondissements/exports/geojson?lang=fr'
const QUARTIERS_URL       = 'https://opendata.paris.fr/api/explore/v2.1/catalog/datasets/quartier_paris/exports/geojson?lang=fr'

const MODES = [
  { key: 'nb_arrets_bus',            label: 'Bus',           icon: '🚌' },
  { key: 'nb_arrets_metro',          label: 'Métro',         icon: '🚇' },
  { key: 'nb_arrets_rer',            label: 'RER',           icon: '🚆' },
  { key: 'nb_arrets_tram',           label: 'Tram',          icon: '🚊' },
  { key: 'nb_arrets_train',          label: 'Train',         icon: '🚂' },
  { key: 'nb_arrets_train_regional', label: 'Régional',      icon: '🚄' },
  { key: 'nb_arrets_funiculaire',    label: 'Funiculaire',   icon: '🚡' },
]

function buildPopupHTML(label, data, indicateurId) {
  if (!data) return `<div class="popup-cp">${label}</div>`
  const score = data.score_mobilite_100 ?? data.score_connectivite_100
              ?? data.score_services_100 ?? data.score_accessibilite_100 ?? '—'
  const header = `
    <div class="popup-cp">${label}</div>
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
      <div class="popup-section-title">Arrêts par mode</div>
      <div class="popup-grid">${modesHTML}</div>
      <div class="popup-divider"></div>
      <div class="popup-section-title">Stationnement</div>
      <div class="popup-grid">
        <div class="popup-stat"><span class="popup-stat-val">${data.nb_bornes ?? 0}</span><span class="popup-stat-lbl">Bornes taxi</span></div>
        <div class="popup-stat"><span class="popup-stat-val">${data.nb_places_gratuit ?? 0}</span><span class="popup-stat-lbl">Gratuit</span></div>
        <div class="popup-stat"><span class="popup-stat-val">${data.nb_places_payant ?? 0}</span><span class="popup-stat-lbl">Payant</span></div>
        <div class="popup-stat"><span class="popup-stat-val">${data.nb_places_2roues ?? 0}</span><span class="popup-stat-lbl">2-roues</span></div>
        <div class="popup-stat"><span class="popup-stat-val">${data.nb_places_pmr ?? 0}</span><span class="popup-stat-lbl">PMR</span></div>
        <div class="popup-stat"><span class="popup-stat-val">${data.nb_places_electrique ?? 0}</span><span class="popup-stat-lbl">Élec.</span></div>
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
        <div class="popup-stat popup-stat-full"><span class="popup-stat-val">${data.operateur_leader ?? '—'}</span><span class="popup-stat-lbl">Opérateur leader</span></div>
      </div>
    `
  }
  if (indicateurId === 'services') {
    const estQuartier = data.code_quartier != null
    let html = header + `
      <div class="popup-section-title">Infrastructures</div>
      <div class="popup-grid">
        <div class="popup-stat"><span class="popup-stat-val">${data.nb_ecoles ?? 0}</span><span class="popup-stat-lbl">Écoles</span></div>
        <div class="popup-stat"><span class="popup-stat-val">${data.nb_commissariats ?? 0}</span><span class="popup-stat-lbl">Commissariats</span></div>
      </div>
    `
    if (!estQuartier) {
      html += `
        <div class="popup-divider"></div>
        <div class="popup-section-title">Commerces locaux</div>
        <div class="popup-grid">
          <div class="popup-stat"><span class="popup-stat-val">${data.nb_commerces_total ?? 0}</span><span class="popup-stat-lbl">Total</span></div>
          <div class="popup-stat"><span class="popup-stat-val">${data.boulangerie ?? 0}</span><span class="popup-stat-lbl">Boulangeries</span></div>
          <div class="popup-stat"><span class="popup-stat-val">${data.supermarche ?? 0}</span><span class="popup-stat-lbl">Supermarchés</span></div>
          <div class="popup-stat"><span class="popup-stat-val">${data.epicerie ?? 0}</span><span class="popup-stat-lbl">Épiceries</span></div>
        </div>
      `
    }
    return html
  }
  if (indicateurId === 'logement') {
    return header + `
      <div class="popup-section-title">Marché immobilier</div>
      <div class="popup-grid">
        <div class="popup-stat"><span class="popup-stat-val">${data.prix_m2_median ?? '—'} €</span><span class="popup-stat-lbl">Prix/m²</span></div>
        <div class="popup-stat"><span class="popup-stat-val">${data.nb_ventes ?? 0}</span><span class="popup-stat-lbl">Ventes</span></div>
        <div class="popup-stat"><span class="popup-stat-val">${data.surface_mediane ?? '—'} m²</span><span class="popup-stat-lbl">Surface méd.</span></div>
      </div>
      <div class="popup-divider"></div>
      <div class="popup-section-title">Social & revenus</div>
      <div class="popup-grid">
        <div class="popup-stat"><span class="popup-stat-val">${data.nb_logements ?? 0}</span><span class="popup-stat-lbl">Log. sociaux</span></div>
        ${data.revenu_median != null ? `<div class="popup-stat"><span class="popup-stat-val">${data.revenu_median} €</span><span class="popup-stat-lbl">Revenu méd.</span></div>` : ''}
        ${data.taux_effort_achat != null ? `<div class="popup-stat"><span class="popup-stat-val">${data.taux_effort_achat}</span><span class="popup-stat-lbl">Effort (ans)</span></div>` : ''}
      </div>
    `
  }
  return header
}

function getArrNum(s) {
  if (s.arrondissement !== undefined) return parseInt(s.arrondissement)
  if (s.code_postal    !== undefined) return parseInt(s.code_postal) - 75000
  return null
}

export default function MapView({
  scores, scoreKey, activeColor, activeIndicateur,
  visibleTypes, selected, onSelect, is3D, loading,
  granularite = 'arrondissement',
  year = null,
}) {
  const mapContainer    = useRef(null)
  const map             = useRef(null)
  const popup           = useRef(null)
  const markersByTypeId = useRef({})
  const allPointsCache  = useRef({})
  const [mapReady, setMapReady]       = useState(false)
  const [zonesLoaded, setZonesLoaded] = useState(0)

  const visibleTypesRef     = useRef(visibleTypes)
  useEffect(() => { visibleTypesRef.current = visibleTypes }, [visibleTypes])
  const activeIndicateurRef = useRef(activeIndicateur)
  useEffect(() => { activeIndicateurRef.current = activeIndicateur }, [activeIndicateur])
  const granulariteRef      = useRef(granularite)
  useEffect(() => { granulariteRef.current = granularite }, [granularite])
  const scoresRef           = useRef(scores)
  useEffect(() => { scoresRef.current = scores }, [scores])
  const onSelectRef         = useRef(onSelect)
  useEffect(() => { onSelectRef.current = onSelect }, [onSelect])
  const selectedRef         = useRef(selected)
  useEffect(() => { selectedRef.current = selected }, [selected])

  const clearMarkers = () => {
    Object.values(markersByTypeId.current).flat().forEach(m => { try { m.remove() } catch (_) {} })
    markersByTypeId.current = {}
  }

  const showMarkersForSelected = (selectedId, gran) => {
    clearMarkers()
    const ind = activeIndicateurRef.current
    if (!selectedId || !ind?.pointTypes) return
    const cacheKey = `${ind.id}_${gran}_${selectedId}`
    const geojson  = allPointsCache.current[cacheKey]
    if (!geojson?.features) return

    const filtered = geojson.features.filter(f => {
      const p = f.properties
      if (gran === 'quartier')
        return parseInt(p.code_quartier) === parseInt(selectedId)
      return parseInt(p.code_postal) === 75000 + parseInt(selectedId) ||
             parseInt(p.arrondissement) === parseInt(selectedId)
    })

    ind.pointTypes.forEach(pointType => {
      const matching = filtered.filter(f => {
        const props = f.properties
        if (props.type !== pointType.mongoType) return false
        if (pointType.modeFilter && props.mode_nom !== pointType.modeFilter) return false
        return true
      })
      if (!matching.length) return
      const isVisible = visibleTypesRef.current.includes(pointType.id)
      markersByTypeId.current[pointType.id] = matching.map(f => {
        const [lng, lat] = f.geometry.coordinates
        const el = document.createElement('div')
        el.style.cssText = `
          width: 10px; height: 10px; border-radius: 50%;
          background: ${pointType.color}; border: 1.5px solid #fff;
          display: ${isVisible ? 'block' : 'none'};
        `
        return new maplibregl.Marker({ element: el }).setLngLat([lng, lat]).addTo(map.current)
      })
    })
  }

  const loadZones = (gran) => {
    if (!map.current) return
    const isQuartier = gran === 'quartier'
    const url = isQuartier ? QUARTIERS_URL : ARRONDISSEMENTS_URL

    ;['zone-3d', 'zone-outline', 'zone-labels'].forEach(id => {
      if (map.current.getLayer(id)) map.current.removeLayer(id)
    })
    if (map.current.getSource('zones')) map.current.removeSource('zones')
    map.current.off('mousemove', 'zone-3d')
    map.current.off('mouseleave', 'zone-3d')
    map.current.off('click',     'zone-3d')

    fetch(url)
      .then(r => r.json())
      .then(geojson => {
        if (!map.current) return
        geojson.features = geojson.features.map(f => {
          const p = f.properties
          const id_zone = isQuartier
            ? parseInt(p.c_qu ?? p.c_quinsee ?? p.code_qu)
            : parseInt(p.c_ar)
          const label_zone = isQuartier
            ? (p.l_qu ?? p.nom_qu ?? p.libelle ?? '')
            : `750${String(p.c_ar).padStart(2, '0')}`
          return { ...f, properties: { ...p, _id_zone: id_zone, _label_zone: label_zone } }
        })

        map.current.addSource('zones', { type: 'geojson', data: geojson })
        map.current.addLayer({ id: 'zone-3d', type: 'fill-extrusion', source: 'zones',
          paint: { 'fill-extrusion-color': '#00d4aa', 'fill-extrusion-height': 100, 'fill-extrusion-base': 0, 'fill-extrusion-opacity': 0.55 }
        })
        map.current.addLayer({ id: 'zone-outline', type: 'line', source: 'zones',
          paint: { 'line-color': '#0a0e1a', 'line-width': isQuartier ? 1 : 1.5 }
        })
        map.current.addLayer({ id: 'zone-labels', type: 'symbol', source: 'zones',
          layout: {
            'text-field': ['get', '_label_zone'], 'text-font': ['Noto Sans Regular'],
            'text-size': isQuartier ? 9 : 11,
            'text-anchor': 'center', 'text-allow-overlap': true, 'text-ignore-placement': true,
            'text-pitch-alignment': 'map', 'text-rotation-alignment': 'map',
          },
          paint: { 'text-color': '#ffffff', 'text-halo-color': '#000000', 'text-halo-width': 2 }
        })

        map.current.on('mousemove', 'zone-3d', (e) => {
          const props  = e.features[0].properties
          const idZone = props._id_zone
          const g      = granulariteRef.current
          const label  = g === 'quartier'
            ? `${props._label_zone} (arr. ${props.c_ar})`
            : `Paris ${idZone}e`
          const data = g === 'quartier'
            ? scoresRef.current.find(s => parseInt(s.code_quartier) === idZone)
            : scoresRef.current.find(s => getArrNum(s) === idZone)
          popup.current.setLngLat(e.lngLat)
            .setHTML(buildPopupHTML(label, data, window.__ude_indicateurId))
            .addTo(map.current)
          map.current.getCanvas().style.cursor = 'pointer'
        })
        map.current.on('mouseleave', 'zone-3d', () => {
          popup.current.remove()
          map.current.getCanvas().style.cursor = ''
        })
        map.current.on('click', 'zone-3d', (e) => {
          const id = e.features[0].properties._id_zone
          if (parseInt(id) === parseInt(selectedRef.current)) {
            onSelectRef.current(null)
          } else {
            onSelectRef.current(id)
          }
        })

        setZonesLoaded(n => n + 1)
      })
      .catch(console.error)
  }

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
        layers: [{ id: 'osm-tiles', type: 'raster', source: 'osm',
          paint: {
            'raster-opacity': ['interpolate', ['linear'], ['zoom'], 11, 0.55, 13, 0.85, 15, 1.0],
            'raster-brightness-min': 0.3,
            'raster-brightness-max': 0.9,
          }
        }]
      },
      center: [2.3488, 48.8534], zoom: 11.5, pitch: 45, bearing: -15, antialias: true,
    })
    map.current.addControl(new maplibregl.NavigationControl(), 'top-right')
    map.current.on('load', () => setMapReady(true))
    return () => { map.current?.remove(); map.current = null }
  }, [])

  useEffect(() => {
    if (!mapReady || !map.current) return
    if (map.current.isStyleLoaded()) {
      loadZones(granularite)
    } else {
      map.current.once('styledata', () => loadZones(granularite))
    }
  }, [mapReady, granularite])

  useEffect(() => {
    window.__ude_scores       = scores
    window.__ude_scoreKey     = scoreKey
    window.__ude_indicateurId = activeIndicateur?.id
  }, [scores, scoreKey, activeIndicateur?.id])

  useEffect(() => {
    if (!mapReady || !map.current || !scores.length || !scoreKey) return
    if (!map.current.getLayer('zone-3d')) return

    const isQuartier = granularite === 'quartier'
    const colorExpr  = ['match', ['get', '_id_zone']]
    const heightExpr = ['match', ['get', '_id_zone']]
    const darkColor  = activeIndicateur?.darkColor ?? '#0d1117'
    const targetId   = selected !== null ? parseInt(selected) : null

    const idsTraites = new Set()
    let aAjouteDesBranches = false

    scores.forEach(s => {
      const id = isQuartier ? parseInt(s.code_quartier) : getArrNum(s)
      if (id === null || isNaN(id) || idsTraites.has(id)) return
      idsTraites.add(id)
      aAjouteDesBranches = true

      const normalized = (s[scoreKey] ?? 0) / 100
      let baseColor = getHeatColor(normalized)
      if (targetId !== null && id !== targetId) {
        baseColor = interpolateColor('#1a2634', baseColor, 0.4)
      }
      colorExpr.push(id, baseColor)
      heightExpr.push(id, is3D ? Math.round(200 + normalized * 1200) : 0)
    })

    if (!aAjouteDesBranches) {
      map.current.setPaintProperty('zone-3d', 'fill-extrusion-color', darkColor)
      map.current.setPaintProperty('zone-3d', 'fill-extrusion-height', 0)
      return
    }

    colorExpr.push(darkColor)
    heightExpr.push(0)

    try {
      map.current.setPaintProperty('zone-3d', 'fill-extrusion-color', colorExpr)
      map.current.setPaintProperty('zone-3d', 'fill-extrusion-height', heightExpr)
      map.current.setPaintProperty('zone-3d', 'fill-extrusion-opacity', is3D ? 0.75 : 0.85)
    } catch (error) {
      console.error("Erreur lors de l'application du style MapLibre:", error)
    }
  }, [scores, scoreKey, activeColor, activeIndicateur?.darkColor, mapReady, is3D, selected, granularite, zonesLoaded])

  // chargement des points pour la zone sélectionnée
  useEffect(() => {
    clearMarkers()
    if (!mapReady || !activeIndicateur?.pointsEndpoint || !selected) return
    const gran     = granularite
    const cacheKey = `${activeIndicateur.id}_${gran}_${selected}`
    const fetcher  = POINTS_FETCHERS[activeIndicateur.id]
    if (!fetcher) return

    if (allPointsCache.current[cacheKey]) {
      showMarkersForSelected(selected, gran)
      return
    }
    const param = gran === 'quartier'
      ? { granularite: 'quartier',       code_quartier:  selected }
      : { granularite: 'arrondissement', arrondissement: selected }
    fetcher(param)
      .then(geojson => {
        allPointsCache.current[cacheKey] = geojson
        showMarkersForSelected(selected, gran)
      })
      .catch(console.error)
  }, [activeIndicateur?.id, mapReady, selected, granularite])

  // LOGEMENT : l'année change -> points d'une autre année invalides -> recharger
  useEffect(() => {
    _currentYear = year
    if (!mapReady) return
    // seuls les indicateurs temporels (points dépendant de l'année) sont concernés
    if (!activeIndicateur?.hasYearFilter || !activeIndicateur?.pointsEndpoint) return
    allPointsCache.current = {}
    if (!selected) { clearMarkers(); return }
    const gran    = granularite
    const fetcher = POINTS_FETCHERS[activeIndicateur.id]
    if (!fetcher) return
    const param = gran === 'quartier'
      ? { granularite: 'quartier',       code_quartier:  selected }
      : { granularite: 'arrondissement', arrondissement: selected }
    fetcher(param)
      .then(geojson => {
        allPointsCache.current[`${activeIndicateur.id}_${gran}_${selected}`] = geojson
        showMarkersForSelected(selected, gran)
      })
      .catch(console.error)
  }, [year])  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    Object.entries(markersByTypeId.current).forEach(([typeId, markers]) => {
      const show = visibleTypes.includes(typeId)
      markers.forEach(m => { m.getElement().style.display = show ? 'block' : 'none' })
    })
  }, [visibleTypes])

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

function getHeatColor(normalized) {
  const colors = [
    { t: 0.0,  hex: '#d73027' },  
    { t: 0.25, hex: '#fc8d59' },
    { t: 0.5,  hex: '#fee08b' },
    { t: 0.75, hex: '#91cf60' },
    { t: 1.0,  hex: '#1a9850' },  
  ]
  for (let i = 0; i < colors.length - 1; i++) {
    const a = colors[i], b = colors[i + 1]
    if (normalized <= b.t) {
      const t2 = (normalized - a.t) / (b.t - a.t)
      return interpolateColor(a.hex, b.hex, t2)
    }
  }
  return colors[colors.length - 1].hex
}

function interpolateColor(hex1, hex2, t) {
  const r1=parseInt(hex1.slice(1,3),16),g1=parseInt(hex1.slice(3,5),16),b1=parseInt(hex1.slice(5,7),16)
  const r2=parseInt(hex2.slice(1,3),16),g2=parseInt(hex2.slice(3,5),16),b2=parseInt(hex2.slice(5,7),16)
  const r=Math.round(r1+(r2-r1)*t),g=Math.round(g1+(g2-g1)*t),b=Math.round(b1+(b2-b1)*t)
  return `#${r.toString(16).padStart(2,'0')}${g.toString(16).padStart(2,'0')}${b.toString(16).padStart(2,'0')}`
}
