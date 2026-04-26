import { Check } from "lucide-react"

interface TagSelectorProps {
  options: { value: string; label: string }[]
  value: string[]
  onChange: (value: string[]) => void
}

export function TagSelector({ options, value, onChange }: TagSelectorProps) {
  return (
    <div className="tag-grid">
      {options.map(option => {
        const selected = value.includes(option.value)
        return (
          <button
            className={selected ? "tag selected" : "tag"}
            key={option.value}
            onClick={() =>
              onChange(
                selected ? value.filter(item => item !== option.value) : [...value, option.value]
              )
            }
            type="button"
          >
            {selected ? <Check size={14} /> : null}
            <span>{option.label}</span>
          </button>
        )
      })}
    </div>
  )
}
