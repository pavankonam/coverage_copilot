import { CalendarCheck, CheckCircle2, UploadCloud } from 'lucide-react'
import { useRef, useState } from 'react'
import { API_BASE_URL } from '../api'
import './RosterUpload.css'

const STEPS = [
  {
    icon: UploadCloud,
    title: 'Upload',
    description: 'Drop your roster CSV here, or browse to select it.',
  },
  {
    icon: CheckCircle2,
    title: 'Validate',
    description: 'Every row is checked against the required columns and shift codes.',
  },
  {
    icon: CalendarCheck,
    title: 'See it on Schedule',
    description: 'Your staff and their weekly shifts appear on the duty board -- right here.',
  },
]

// Embedded in SchedulePage's empty state (no roster loaded yet). On a
// successful upload, calls onUploaded(body) and steps back -- it has no
// "success" display of its own; the caller (SchedulePage) refetches and
// shows the actual duty board in the same place, which is the real
// confirmation.
//
// onCancel is optional: passed only when this is shown via "Replace
// roster" on top of an already-loaded board (there's something to
// cancel back to). The plain empty state has nothing to return to, so
// it omits onCancel and no Cancel button renders.
function RosterUpload({ onUploaded, onCancel }) {
  const [state, setState] = useState({ status: 'idle' })
  const [isDragging, setIsDragging] = useState(false)
  const fileInputRef = useRef(null)

  async function handleFile(file) {
    if (!file) return
    setState({ status: 'uploading', fileName: file.name })

    const formData = new FormData()
    formData.append('file', file)

    try {
      const response = await fetch(`${API_BASE_URL}/roster`, {
        method: 'POST',
        body: formData,
      })

      let body = null
      try {
        body = await response.json()
      } catch {
        // No JSON body -- fall back to a status-based message below.
      }

      if (!response.ok) {
        throw new Error(body?.detail ?? `Request failed (${response.status})`)
      }

      if (!body.success) {
        setState({ status: 'invalid', errors: body.errors, staffCount: body.staff_count })
        return
      }

      setState({ status: 'idle' })
      onUploaded(body)
    } catch (err) {
      setState({
        status: 'error',
        message:
          err instanceof TypeError
            ? "Couldn't reach the API. Check your connection and try again."
            : err.message,
      })
    }
  }

  function handleDragOver(event) {
    event.preventDefault()
    setIsDragging(true)
  }

  function handleDragLeave(event) {
    event.preventDefault()
    setIsDragging(false)
  }

  function handleDrop(event) {
    event.preventDefault()
    setIsDragging(false)
    handleFile(event.dataTransfer.files?.[0])
  }

  function handleInputChange(event) {
    handleFile(event.target.files?.[0])
    event.target.value = '' // allow re-selecting the same file later
  }

  const showDropzone = state.status === 'idle' || state.status === 'invalid' || state.status === 'error'

  return (
    <div>
      <div className="upload-card">
        <h2 className="upload-card-heading">Upload your roster</h2>
        <p className="upload-card-subheading">
          A CSV with staff, weekly schedule, and availability.
        </p>

        {state.status === 'invalid' && (
          <div className="error-box-on-ink upload-errors" role="alert">
            <p className="upload-errors-headline">
              {state.errors.length} issue{state.errors.length === 1 ? '' : 's'} found — fix and
              re-upload.
            </p>
            <ul className="upload-errors-list">
              {state.errors.map((message, index) => (
                <li key={index}>{message}</li>
              ))}
            </ul>
            {state.staffCount > 0 && (
              <p className="upload-errors-note">
                {state.staffCount} staff loaded successfully despite the issue
                {state.errors.length === 1 ? '' : 's'} above.
              </p>
            )}
          </div>
        )}

        {state.status === 'error' && (
          <p className="error-box-on-ink upload-generic-error" role="alert">
            {state.message}
          </p>
        )}

        {state.status === 'uploading' && (
          <p className="upload-uploading">Uploading {state.fileName}…</p>
        )}

        {showDropzone && (
          <label
            className={'dropzone' + (isDragging ? ' dropzone-active' : '')}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,text/csv"
              className="sr-only"
              onChange={handleInputChange}
            />
            <UploadCloud className="dropzone-icon" size={30} strokeWidth={1.5} aria-hidden="true" />
            <span className="dropzone-title">Drag and drop your roster CSV here</span>
            <span className="dropzone-subtitle">or click to browse files</span>
          </label>
        )}

        {onCancel && (
          <button
            type="button"
            className="btn btn-ghost-on-ink upload-cancel-button"
            onClick={onCancel}
            disabled={state.status === 'uploading'}
          >
            Cancel
          </button>
        )}
      </div>

      <ol className="upload-steps">
        {STEPS.map(({ icon: Icon, title, description }) => (
          <li key={title} className="upload-step">
            <div className="upload-step-icon">
              <Icon size={18} strokeWidth={1.75} aria-hidden="true" />
            </div>
            <p className="upload-step-title">{title}</p>
            <p className="upload-step-description">{description}</p>
          </li>
        ))}
      </ol>
    </div>
  )
}

export default RosterUpload
