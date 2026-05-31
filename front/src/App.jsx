import { useState, useEffect } from 'react'
import MapView  from './components/MapView'
import Sidebar  from './components/Sidebar'
import { INDICATEURS } from './indicateurs/index'
import { useScores }   from './hooks/useScores'
import './index.css'

export default function App() {
  const [activeIndicateur, setActiveIndicateur] = useState(INDICATEURS[0])
  const [selected, setSelected] = useState(null)
  const [is3D, setIs3D]         = useState(true)
  const [visibleTypes, setVisibleTypes] = useState(
    INDICATEURS[0].pointTypes?.map(p => p.id) ?? []
  )
  const [year, setYear] = useState(null)

  const { scores, loading } = useScores(activeIndicateur, year)

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
        onSelectIndicateur={(ind) => { setActiveIndicateur(ind); setSelected(null) }}
        selected={selected}
        scores={scores}
        visibleTypes={visibleTypes}
        onToggleType={handleToggleType}
        year={year}
        onYearChange={setYear}
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
      />
    </div>
  )
}