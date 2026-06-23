// src/api/services.js

const API = 'http://localhost:8000'
const headers = { 'X-API-Key': import.meta.env.VITE_API_KEY }

export async function fetchScoresServices() {
  const res = await fetch(`${API}/services`, { headers })
  if (!res.ok) throw new Error(`Erreur ${res.status}`)
  return res.json()
}

export async function fetchPointsServices(codePostal = null) {
  const url = codePostal
    ? `${API}/services/points/geojson?code_postal=${codePostal}`
    : `${API}/services/points/geojson`
  const res = await fetch(url, { headers })
  if (!res.ok) throw new Error(`Erreur ${res.status}`)
  return res.json()
}