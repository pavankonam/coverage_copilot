// Mirrors src/data_layer.py's DEFAULT_DEPARTMENTS and the four
// department tag colors defined in styles/tokens.css. Shared by
// SchedulePage and the Pending review cards.
const DEPARTMENT_COLOR_VAR = {
  'Front Desk': '--color-dept-front-desk',
  Housekeeping: '--color-dept-housekeeping',
  'F&B': '--color-dept-fb',
  Concierge: '--color-dept-concierge',
}

export function departmentColorVar(department) {
  return DEPARTMENT_COLOR_VAR[department] ?? '--color-text-muted'
}
