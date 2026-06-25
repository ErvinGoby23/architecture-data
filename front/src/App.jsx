import { useState, useEffect } from 'react'
import MapView  from './components/MapView'
import Sidebar  from './components/Sidebar'
import { INDICATEURS } from './indicateurs/index'
import { fetchScoresMobilite, fetchScoresConnectivite, fetchScoresServices, fetchScoresVivabilite, fetchScoresLogement } from './api/index'
import './index.css'
import RankingPanel from './components/RankingPanel'
import ComparePanel from './components/ComparePanel'
import BandeauLogement from './components/BandeauLogement'

const SCORES_FETCHERS = {
  mobilite:     fetchScoresMobilite,
  connectivite: fetchScoresConnectivite,
  services:     fetchScoresServices,
  vivabilite:   fetchScoresVivabilite,
  logement:     fetchScoresLogement,
}

export default function App() {
  const [activeIndicateur, setActiveIndicateur] = useState(INDICATEURS[0])
  const [selected, setSelected]   = useState(null)
  const [is3D, setIs3D]           = useState(true)
  const [visibleTypes, setVisibleTypes] = useState(
    INDICATEURS[0].pointTypes?.map(p => p.id) ?? []
  )
  const [granularite, setGranularite] = useState('arrondissement')
  const [year, setYear] = useState(
  INDICATEURS[0].hasYearFilter ? (INDICATEURS[0].defaultYear ?? 2025) : null
  )
  const [refreshKey, setRefreshKey] = useState(0)
  const [scores, setScores]       = useState([])
  const [loading, setLoading]     = useState(true)
  const [compareMode, setCompareMode] = useState(false)
  const [compareList, setCompareList] = useState([])

  useEffect(() => {
    const fetcher = SCORES_FETCHERS[activeIndicateur.id]
    if (!fetcher) return
    setLoading(true)
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

  const handleSelect = (id) => {
    if (!compareMode) {
      setSelected(id)
      return
    }
    setCompareList(prev => {
      if (prev.includes(id)) return prev
      if (prev.length >= 3) return prev
      return [...prev, id]
    })
  }

  return (
    <div className="app">
      <header className="header">
        <div className="header-logo">
          <span className="badge">UD</span>
          <h1>Urban Data Explorer</h1>
        </div>
        <div className="header-controls">
          <button
            className={`btn-toggle ${compareMode ? 'active' : ''}`}
            onClick={() => { setCompareMode(v => !v); setCompareList([]) }}
          >
            ⚖ Comparer
          </button>
          <button className={`btn-toggle ${is3D ? 'active' : ''}`} onClick={() => setIs3D(v => !v)}>
            {is3D ? '3D' : '2D'}
          </button>
        </div>
      </header>

      <Sidebar
        indicateurs={INDICATEURS}
        activeIndicateur={activeIndicateur}
        onSelectIndicateur={(ind) => {
          setActiveIndicateur(ind)
          setSelected(null)
          // indicateur temporel -> année par défaut (la plus récente) ; sinon null
          setYear(ind.hasYearFilter ? (ind.defaultYear ?? 2025) : null)
        }}        selected={selected}
        scores={scores}
        visibleTypes={visibleTypes}
        onToggleType={handleToggleType}
        year={year}
        onYearChange={handleYearChange}
        granularite={granularite}
        onGranulariteChange={(g) => { setGranularite(g); setSelected(null) }}
      />

      <div style={{ position: 'relative', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <div style={{ position: 'relative', flex: 1, overflow: 'hidden' }}>
          <MapView
            scores={scores}
            year={year}
            scoreKey={activeIndicateur.scoreKey}
            activeColor={activeIndicateur.color}
            activeIndicateur={activeIndicateur}
            visibleTypes={visibleTypes}
            selected={selected}
            onSelect={handleSelect}
            is3D={is3D}
            loading={loading}
            granularite={granularite}
          />
          <RankingPanel
            scores={scores}
            activeIndicateur={activeIndicateur}
            granularite={granularite}
            onSelect={handleSelect}
            selected={selected}
          />
        </div>

        {compareMode && (
          <ComparePanel
            compareList={compareList}
            scores={scores}
            activeIndicateur={activeIndicateur}
            granularite={granularite}
            onRemove={(id) => setCompareList(prev => prev.filter(i => i !== id))}
            onClear={() => { setCompareList([]); setCompareMode(false) }}
          />
        )}
      </div>
    </div>
  )
}
