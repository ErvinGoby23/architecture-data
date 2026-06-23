export const connectivite = {
  id: 'connectivite',
  label: 'Connectivité',
  sub: 'Fibre & antennes',
  color: '#4f8ef7',
  darkColor: '#0d1117',
  hasQuartier: true,

  endpoint: {
    arrondissement: '/connectivite',
    quartier:       '/connectivite/quartier',
  },
  pointsEndpoint: '/connectivite/points/geojson',

  scoreKey: 'score_connectivite_100',
  disabled: false,
  hasYearFilter: false,

  pointTypes: [
    { id: 'antenne', label: 'Antennes relais', color: '#4f8ef7', mongoType: 'antenne' },
  ],

  scoreBars: (data) => [
    { label: 'Fibre (%)',  value: (data.taux_fibre ?? 0) / 100 },
    { label: '5G (%)',     value: (data.taux_5g    ?? 0) / 100 },
    { label: '4G (%)',     value: (data.taux_4g    ?? 0) / 100 },
  ],

  stats: (data) => [
    { label: 'Total antennes',   value: data.nb_antennes,      unit: '' },
    { label: '5G',               value: data.nb_antennes_5g,   unit: '' },
    { label: '4G',               value: data.nb_antennes_4g,   unit: '' },
    { label: '3G',               value: data.nb_antennes_3g,   unit: '' },
    { label: '2G',               value: data.nb_antennes_2g,   unit: '' },
    { label: 'Fibre',            value: data.taux_fibre,        unit: '%' },
    { label: 'Opérateur leader', value: data.operateur_leader,  unit: '' },
  ]
}