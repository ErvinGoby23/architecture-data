import { useState, useEffect } from 'react'

const API = 'http://localhost:8000'

export function useScores(indicateur, year = null) {
  const [scores, setScores]   = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!indicateur?.endpoint) return
    setLoading(true)

    const query = year ? `?year=${year}` : ''

    fetch(`${API}${indicateur.endpoint}${query}`)
      .then(r => r.json())
      .then(data => { setScores(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [indicateur?.id, year])

  return { scores, loading }
}