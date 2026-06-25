// ==========================================================================
// CONFIG — Indicateur Logement (à ajouter à votre tableau d'indicateurs)
// ==========================================================================
// Champs consommés par MapView / Sidebar :
//   id, label, color, darkColor, scoreKey, hasYearFilter,
//   pointsEndpoint, pointTypes[{id,label,color,mongoType,modeFilter}], scoreBars(data)

export const logement = {
  id: 'logement',
  label: 'Logement',
  icon: '🏠',
  color: '#6366f1',
  darkColor: '#0d1117',

  // score affiché (correspond à la colonne du Gold)
  scoreKey: 'score_accessibilite_100',

  // logement = données temporelles -> active le filtre année
  hasYearFilter: true,

  // active le chargement des points (clé présente = MapView tente le fetch)
  pointsEndpoint: true,

  // deux types de points dans la collection Mongo silver.indicateur_logement
  pointTypes: [
    { id: 'transaction',     label: 'Ventes (DVF)',       color: '#f59e0b', mongoType: 'transaction' },
    { id: 'logement_social', label: 'Logements sociaux',  color: '#10b981', mongoType: 'logement_social' },
  ],

  // barres de détail dans la Sidebar (valeurs normalisées 0..1)
  scoreBars: (d) => ([
    { label: 'Prix accessible', value: d.score_prix   ?? 0 },
    { label: 'Part sociale',    value: d.score_social  ?? 0 },
    // score_revenu n'existe qu'à l'arrondissement (pas au quartier)
    ...(d.score_revenu != null ? [{ label: 'Capacité d\'achat', value: d.score_revenu }] : []),
  ]),
}
