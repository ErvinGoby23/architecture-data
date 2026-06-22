import { useState, useEffect } from 'react'
import MapView  from './components/MapView'
import Sidebar  from './components/Sidebar'
import { INDICATEURS } from './indicateurs/index'
import { fetchScoresMobilite, fetchScoresConnectivite } from './api/index'
import './index.css'

const SCORES_FETCHERS = {
  mobilite:     fetchScoresMobilite,
  connectivite: fetchScoresConnectivite,
}

export default function App() {
  const [activeIndicateur, setActiveIndicateur] = useState(INDICATEURS[0])
  const [selected, setSelected]   = useState(null)
  const [is3D, setIs3D]           = useState(true)
  const [granularite, setGranularite] = useState('arrondissement') // 'arrondissement' | 'quartier'
  const [visibleTypes, setVisibleTypes] = useState(
    INDICATEURS[0].pointTypes?.map(p => p.id) ?? []
  )
  const [year, setYear]           = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [scores, setScores]       = useState([])
  const [loading, setLoading]     = useState(true)

  useEffect(() => {
    const fetcher = SCORES_FETCHERS[activeIndicateur.id]
    if (!fetcher) return
    setLoading(true)

    // Pour mobilité → passe la granularité
    // Pour connectivité → passe juste l'année (ancienne signature)
    const params = activeIndicateur.id === 'mobilite'
      ? { granularite }
      : (activeIndicateur.hasYearFilter ? year : undefined)

    fetcher(params)
      .then(data => { setScores(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [activeIndicateur.id, year, refreshKey, granularite])

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

  const handleGranulariteChange = (g) => {
    setGranularite(g)
    setSelected(null) // reset sélection au changement de granularité
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

      <Sidebar
        indicateurs={INDICATEURS}
        activeIndicateur={activeIndicateur}
        onSelectIndicateur={(ind) => { setActiveIndicateur(ind); setSelected(null); setYear(null); if (!ind.hasQuartier) setGranularite('arrondissement') }}
        selected={selected}
        scores={scores}
        visibleTypes={visibleTypes}
        onToggleType={handleToggleType}
        year={year}
        onYearChange={handleYearChange}
        granularite={granularite}
        onGranulariteChange={activeIndicateur.id === 'mobilite' ? handleGranulariteChange : null}
      />

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
