// src/indicateurs/services.js

export const services = {
  id: 'services', // Doit matcher la clé dans MapView
  label: 'Services',
  sub: 'Écoles, Commerces & Sécurité',
  color: '#eab308', // Un jaune/doré pour se démarquer
  endpoint: '/services',
  pointsEndpoint: '/services/points/geojson',
  scoreKey: 'score_services_100',
  disabled: false,
  hasYearFilter: false,

  // Les filtres cliquables sur le côté de la carte
  pointTypes: [
    { id: 'ecole', label: 'Écoles élémentaires', color: '#3b82f6', mongoType: 'ecole' }, // Bleu
    { id: 'commissariat', label: 'Commissariats', color: '#ef4444', mongoType: 'commissariat' }, // Rouge
  ],

  // Les barres de progression sous le score (basées sur les valeurs 0-1)
  // En mode quartier, il n'y a PAS de commerces (gold quartier = écoles + commissariats).
  // On détecte la granularité via la présence de code_quartier dans data.
  scoreBars: (data) => {
    const estQuartier = data?.code_quartier != null
    if (estQuartier) {
      return [
        { label: 'Écoles',        value: data.score_ecoles ?? 0 },
        { label: 'Commissariats', value: data.score_commissariats ?? 0 },
      ]
    }
    return [
      { label: 'Commerces',     value: data.score_commerces ?? 0 },
      { label: 'Écoles',        value: data.score_ecoles ?? 0 },
      { label: 'Commissariats', value: data.score_commissariats ?? 0 },
    ]
  },

  // Les statistiques détaillées du panneau latéral
  stats: (data) => {
    const estQuartier = data?.code_quartier != null
    if (estQuartier) {
      return [
        { label: 'Écoles',           value: data.nb_ecoles,            unit: '' },
        { label: 'Commissariats',    value: data.nb_commissariats,     unit: '' },
        { label: 'Écoles / km²',     value: data.ecoles_par_km2,       unit: '' },
        { label: 'Commissariats/km²',value: data.commissariats_par_km2,unit: '' },
      ]
    }
    return [
      { label: 'Total Commerces',  value: data.nb_commerces_total, unit: '' },
      { label: 'Supermarchés',     value: data.supermarche,        unit: '' },
      { label: 'Boulangeries',     value: data.boulangerie,        unit: '' },
      { label: 'Écoles',           value: data.nb_ecoles,          unit: '' },
      { label: 'Commissariats',    value: data.nb_commissariats,   unit: '' },
      { label: 'Écoles / km²',     value: data.ecoles_par_km2,     unit: '' },
      { label: 'Commerces / km²',  value: data.commerces_par_km2,  unit: '' },
    ]
  },
}