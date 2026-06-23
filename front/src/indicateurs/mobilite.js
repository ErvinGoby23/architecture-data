export const mobilite = {
  id: 'mobilite',
  label: 'Mobilité',
  sub: 'Transports & stationnement',
  color: '#00d4aa',
  darkColor: '#0d1117',

  // Endpoints selon granularité
  endpoint: {
    arrondissement: '/mobilite',
    quartier:       '/mobilite/quartier',
  },
  pointsEndpoint: '/mobilite/points/geojson',

  scoreKey: 'score_mobilite_100',
  hasYearFilter: false,
  disabled: false,
  hasQuartier: true,

  pointTypes: [
    { id: 'arret_bus',            label: 'Bus',            color: '#00d4aa', mongoType: 'arret',      modeFilter: 'Bus' },
    { id: 'arret_metro',          label: 'Métro',          color: '#4f8ef7', mongoType: 'arret',      modeFilter: 'Métro' },
    { id: 'arret_rer',            label: 'RER',            color: '#f7e04f', mongoType: 'arret',      modeFilter: 'RER' },
    { id: 'arret_tram',           label: 'Tram',           color: '#ff6b6b', mongoType: 'arret',      modeFilter: 'Tram' },
    { id: 'arret_train',          label: 'Train',          color: '#ffa94d', mongoType: 'arret',      modeFilter: 'Train' },
    { id: 'arret_train_regional', label: 'Train Régional', color: '#cc5de8', mongoType: 'arret',      modeFilter: 'Train Régional' },
    { id: 'borne_taxi',           label: 'Bornes taxi',    color: '#f7e04f', mongoType: 'borne_taxi' },
    { id: 'gratuit',              label: 'Parking gratuit',color: '#a8ff78', mongoType: 'gratuit' },
    { id: 'payant',               label: 'Parking payant', color: '#ff6b6b', mongoType: 'payant' },
    { id: '2roues',               label: '2-Roues',        color: '#ffa94d', mongoType: '2roues' },
    { id: 'pmr',                  label: 'PMR',            color: '#74c0fc', mongoType: 'pmr' },
    { id: 'electrique',           label: 'Électrique',     color: '#cc5de8', mongoType: 'electrique' },
  ],

  scoreBars: (data) => [
    { label: 'Arrêts (%)',        value: data.taux_arrets    / 100 },
    { label: 'Lignes (%)',        value: data.taux_lignes    / 100 },
    { label: 'Taxi (%)',          value: data.taux_taxi      / 100 },
    { label: 'Stationnement (%)', value: data.taux_gratuit   / 100 },
    { label: '2-Roues (%)',       value: data.taux_2roues    / 100 },
    { label: 'PMR (%)',           value: data.taux_pmr       / 100 },
    { label: 'Électrique (%)',    value: data.taux_electrique/ 100 },
  ],
}