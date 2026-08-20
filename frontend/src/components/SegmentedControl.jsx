import './SegmentedControl.css'

function SegmentedControl({ value, onChange, options }) {
  return (
    <div className="segmented-control" role="tablist">
      {options.map((option) => {
        const isActive = value === option.value
        return (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={isActive}
            className={'segmented-control-option' + (isActive ? ' segmented-control-option-active' : '')}
            onClick={() => onChange(option.value)}
          >
            {option.label}
            {option.count != null && (
              <span className="segmented-control-count">{option.count}</span>
            )}
          </button>
        )
      })}
    </div>
  )
}

export default SegmentedControl
