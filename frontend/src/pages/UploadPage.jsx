import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { API_BASE_URL } from '../api'
import './UploadPage.css'

function UploadPage() {
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

      // The upload response itself doesn't include a department
      // breakdown, only staff_count -- fetch /schedule for that. Not
      // critical: the upload already succeeded either way, so a failure
      // here just means a shorter summary, not an error state.
      let departments = []
      try {
        const scheduleResponse = await fetch(`${API_BASE_URL}/schedule`)
        if (scheduleResponse.ok) {
          const scheduleData = await scheduleResponse.json()
          departments = [...new Set(scheduleData.original.map((row) => row.department))].sort()
        }
      } catch {
        // Non-critical, see above.
      }

      setState({ status: 'success', staffCount: body.staff_count, departments })
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

  function reset() {
    setState({ status: 'idle' })
  }

  const showDropzone = state.status === 'idle' || state.status === 'invalid' || state.status === 'error'

  return (
    <div>
      <h1 className="page-heading">Upload</h1>

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

        {state.status === 'success' && (
          <div className="upload-success">
            <p className="upload-success-headline">Roster loaded successfully.</p>
            <p className="upload-success-summary">
              {state.staffCount} staff loaded
              {state.departments.length > 0 && (
                <>
                  {' '}
                  across {state.departments.length} department
                  {state.departments.length === 1 ? '' : 's'}: {state.departments.join(', ')}
                </>
              )}
              .
            </p>
            <div className="upload-success-actions">
              <Link to="/schedule" className="btn btn-primary">
                Go to Schedule
              </Link>
              <button type="button" className="btn btn-ghost-on-ink" onClick={reset}>
                Upload a different file
              </button>
            </div>
          </div>
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
            <span className="dropzone-title">Drag and drop your roster CSV here</span>
            <span className="dropzone-subtitle">or click to browse files</span>
          </label>
        )}
      </div>
    </div>
  )
}

export default UploadPage
