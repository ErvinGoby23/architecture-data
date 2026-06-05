import { useState, useEffect } from 'react'

const API = 'http://localhost:8000'
const API_KEY = import.meta.env.VITE_API_KEY

export function useScores(indicateur, year = null) {
  const [scores, setScores]   = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!indicateur?.endpoint) return
    setLoading(true)

    const query = year ? `?year=${year}` : ''

    fetch(`${API}${indicateur.endpoint}${query}`, {
      headers: { 'X-API-Key': API_KEY }
    })
      .then(r => r.json())
      .then(data => { setScores(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [indicateur?.id, year])

  return { scores, loading }
}