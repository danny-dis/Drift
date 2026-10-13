import { useRef } from "react";
import type { KeyboardEvent } from "react";

type Props<T extends string> = {
  tabs: readonly { id: T; label: string }[];
  selected: T;
  onSelect: (id: T) => void;
};

export default function SectionTabs<T extends string>({ tabs, selected, onSelect }: Props<T>) {
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  const navigate = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let next: number;
    switch (event.key) {
      case "ArrowRight": next = (index + 1) % tabs.length; break;
      case "ArrowLeft": next = (index - 1 + tabs.length) % tabs.length; break;
      case "Home": next = 0; break;
      case "End": next = tabs.length - 1; break;
      default: return;
    }
    event.preventDefault();
    onSelect(tabs[next].id);
    buttons.current[next]?.focus();
  };
  return (
    <nav className="tabs" role="tablist" aria-label="Drift sections" aria-orientation="horizontal">
      {tabs.map((tab, index) => (
        <button key={tab.id} type="button" role="tab" id={`drift-tab-${tab.id}`}
          aria-controls={`drift-panel-${tab.id}`} aria-selected={selected === tab.id}
          tabIndex={selected === tab.id ? 0 : -1}
          ref={button => { buttons.current[index] = button; }}
          className={selected === tab.id ? "tab active" : "tab"}
          onClick={() => onSelect(tab.id)} onKeyDown={event => navigate(event, index)}>{tab.label}</button>
      ))}
    </nav>
  );
}
