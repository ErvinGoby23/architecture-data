// À ajouter dans indicateurs/index.js (même pattern que mobilite)

export const vivabilite = {
  id: 'vivabilite',
  label: 'Vivabilité',
  sub: 'Environnement & qualité de vie',
  color: '#4ade80',
  darkColor: '#0a1a0d',

  endpoint: {
    arrondissement: '/vivabilite',
    quartier:       '/vivabilite/quartier',
  },
  pointsEndpoint: '/vivabilite/points/geojson',

  scoreKey: 'score_vivabilite_100',
  hasYearFilter: false,
  disabled: false,
  hasQuartier: true,

pointTypes: [
  { id: 'espace_vert',                            label: 'Espaces verts',   color: '#4ade80', mongoType: 'espace_vert' },
  { id: 'Propreté',                               label: 'Propreté',        color: '#f87171', mongoType: 'Propreté' },
  { id: 'Graffitis, tags, affiches et autocollants', label: 'Graffitis',   color: '#fb923c', mongoType: 'Graffitis, tags, affiches et autocollants' },
  { id: 'Autos, motos, vélos, trottinettes...',   label: 'Véhicules',       color: '#a78bfa', mongoType: 'Autos, motos, vélos, trottinettes...' },
  { id: 'Mobiliers urbains',                      label: 'Mobilier urbain', color: '#60a5fa', mongoType: 'Mobiliers urbains' },
],

  scoreBars: (data) => [
    { label: 'Propreté',      value: data.score_proprete },
    { label: 'Espaces verts', value: data.score_espaces_verts },
    { label: 'Criminalité',   value: data.score_criminalite },
    { label: 'NO2',           value: data.score_no2 },
  ].filter(b => b.value != null),
  }