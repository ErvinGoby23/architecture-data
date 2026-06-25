// src/indicateurs/vivabilite.js

export const vivabilite = {
  id: 'vivabilite',
  label: 'Vivabilité',
  sub: 'Bruit, Air, Propreté & Nature',
  color: '#22c55e',
  darkColor: '#0d1117',
  hasQuartier: true,

  endpoint: {
    arrondissement: '/vivabilite',
    quartier:       '/vivabilite/quartier',
  },
  // Pas de pointsEndpoint pour l'instant (GeoJSON MongoDB non activé)
  pointsEndpoint: '/vivabilite/points/geojson',

  scoreKey: 'score_vivabilite_100',
  disabled: false,
  hasYearFilter: false,

  // Pas de pointTypes (pas d'endpoint GeoJSON actif)
  pointTypes: [
    { id: 'signalement', label: 'Signalements propreté', color: '#f97316', mongoType: 'signalement' },
    { id: 'espace_vert', label: 'Espaces verts',         color: '#22c55e', mongoType: 'espace_vert' },
  ],

  // ⚠️ En mode quartier : seulement propreté + espaces verts disponibles
  scoreBars: (data) => {
    const estQuartier = data?.code_quartier != null
    if (estQuartier) {
      return [
        { label: 'Propreté',       value: (data.score_proprete      ?? 0) / 100 },
        { label: 'Espaces verts',  value: (data.score_espaces_verts ?? 0) / 100 },
      ]
    }
    return [
      { label: 'Propreté',       value: (data.score_proprete      ?? 0) / 100 },
      { label: 'Espaces verts',  value: (data.score_espaces_verts ?? 0) / 100 },
      { label: 'Criminalité',    value: (data.score_criminalite   ?? 0) / 100 },
      { label: 'Bruit',          value: (data.score_bruit         ?? 0) / 100 },
      { label: 'NO₂',            value: (data.score_no2           ?? 0) / 100 },
    ]
  },

  stats: (data) => {
    const estQuartier = data?.code_quartier != null
    if (estQuartier) {
      return [
        { label: 'Signalements propreté', value: data.nb_signalements,    unit: '' },
        { label: 'Espaces verts',         value: data.nb_espaces_verts,   unit: '' },
        { label: 'Surface verte',         value: data.surface_totale_m2
            ? Math.round(data.surface_totale_m2 / 10_000) : null,          unit: 'ha' },
      ]
    }
    return [
      { label: 'Signalements propreté', value: data.nb_signalements,    unit: '' },
      { label: 'Espaces verts',         value: data.nb_espaces_verts,   unit: '' },
      { label: 'Surface verte',         value: data.surface_totale_m2
          ? Math.round(data.surface_totale_m2 / 10_000) : null,          unit: 'ha' },
      { label: 'Taux crime (‰)',        value: data.taux_crime_global,  unit: '‰' },
      { label: 'Bruit Lden',            value: data.bruit_lden_moy_db,  unit: 'dB' },
      { label: 'NO₂ moy.',              value: data.no2_periphe_moy,    unit: 'µg/m³' },
    ]
  },
}
