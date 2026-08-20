import { departmentColorVar } from '../departmentColors'
import './DeptTag.css'

function DeptTag({ department }) {
  return (
    <span className="dept-tag" style={{ '--dept-color': `var(${departmentColorVar(department)})` }}>
      {department}
    </span>
  )
}

export default DeptTag
