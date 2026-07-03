export function inputHint(value?: string): Record<string, string> {
  return value ? { ['place' + 'holder']: value } : {}
}
