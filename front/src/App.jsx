import { useState, useEffect } from 'react'
import MapView  from './components/MapView'
import Sidebar  from './components/Sidebar'
import { INDICATEURS } from './indicateurs/index'
// 1. On ajoute l'import de fetchScoresServices
import { fetchScoresMobilite, fetchScoresConnectivite, fetchScoresServices } from './api/index'
import './index.css'

// 2. On ajoute 'services' au dictionnaire des fetchers
const SCORES_FETCHERS = {
  mobilite:     fetchScoresMobilite,
  connectivite: fetchScoresConnectivite,
  services:     fetchScoresServices, 
}

export default function App() {
  const [activeIndicateur, setActiveIndicateur] = useState(INDICATEURS[0])
  const [selected, setSelected] = useState(null)
  const [is3D, setIs3D]         = useState(true)
  const [visibleTypes, setVisibleTypes] = useState(
    INDICATEURS[0].pointTypes?.map(p => p.id) ?? []
  )
  const [granularite, setGranularite] = useState('arrondissement') // 1. Lifted state
  const [year, setYear]           = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [scores, setScores]       = useState([])
  const [loading, setLoading]     = useState(true)

  // 2. Included granularite in API fetcher dependency array
  useEffect(() => {
    const fetcher = SCORES_FETCHERS[activeIndicateur.id]
    if (!fetcher) return
    setLoading(true)
    
    // Pass granularite to your backend fetcher alongside the year filter
    fetcher({ 
      granularite, 
      year: activeIndicateur.hasYearFilter ? year : null 
    })
      .then(data => { setScores(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [activeIndicateur.id, granularite, year, refreshKey])

  useEffect(() => {
    setVisibleTypes(activeIndicateur.pointTypes?.map(p => p.id) ?? [])
  }, [activeIndicateur.id])

  const handleToggleType = (typeId) => {
    setVisibleTypes(prev =>
      prev.includes(typeId)
        ? prev.filter(t => t !== typeId)
        : [...prev, typeId]
    )
  }

  const handleYearChange = (y) => {
    setYear(y)
    setRefreshKey(k => k + 1)
  }

  return (
    <div className="app">
      <header className="header">
        <div className="header-logo">
          <span className="badge">UD</span>
          <h1>Urban Data Explorer</h1>
        </div>
        <div className="header-controls">
          <button className={`btn-toggle ${is3D ? 'active' : ''}`} onClick={() => setIs3D(v => !v)}>
            {is3D ? '3D' : '2D'}
          </button>
        </div>
      </header>

      {/* 3. Pass state and setter down to Sidebar */}
      <Sidebar
        indicateurs={INDICATEURS}
        activeIndicateur={activeIndicateur}
        onSelectIndicateur={(ind) => { setActiveIndicateur(ind); setSelected(null); setYear(null) }}
        selected={selected}
        scores={scores}
        visibleTypes={visibleTypes}
        onToggleType={handleToggleType}
        year={year}
        onYearChange={handleYearChange}
        granularite={granularite}
        onGranulariteChange={(g) => { setGranularite(g); setSelected(null); }} 
      />

      {/* 4. Pass down to MapView so map layers update synchronously */}
      <MapView
        scores={scores}
        scoreKey={activeIndicateur.scoreKey}
        activeColor={activeIndicateur.color}
        activeIndicateur={activeIndicateur}
        visibleTypes={visibleTypes}
        selected={selected}
        onSelect={setSelected}
        is3D={is3D}
        loading={loading}
        granularite={granularite}
      />
    </div>
  )
}