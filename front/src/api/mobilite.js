const API = 'http://localhost:8000'
const headers = { 'X-API-Key': import.meta.env.VITE_API_KEY }

export async function fetchScoresMobilite() {
  const res = await fetch(`${API}/mobilite`, { headers })
  if (!res.ok) throw new Error(`Erreur ${res.status}`)
  return res.json()
}

export async function fetchPointsMobilite() {
  const res = await fetch(`${API}/mobilite/points/geojson`, { headers })
  if (!res.ok) throw new Error(`Erreur ${res.status}`)
  return res.json()
}