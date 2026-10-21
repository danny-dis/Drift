import { useRef } from "react";
import {routeHref, type Section} from "./navigation";
import type { KeyboardEvent } from "react";

type Props<T extends string> = {
  tabs: readonly { id: T; label: string }[];
  selected: T;
  onSelect: (id: T) => void;
};

export default function SectionTabs<T extends string>({ tabs, selected, onSelect }: Props<T>) {
  const buttons = useRef<(HTMLAnchorElement | null)[]>([]);
  const navigate = (event: KeyboardEvent<HTMLAnchorElement>, index: number) => {
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
    <>
    <nav className="mobile-navigation" aria-label="Drift pages"><label htmlFor="mobile-section">Go to page</label><select id="mobile-section" value={selected} onChange={event=>onSelect(event.target.value as T)}>{tabs.map(tab=><option key={tab.id} value={tab.id}>{tab.label}</option>)}</select></nav>
    <nav className="tabs" role="tablist" aria-label="Drift sections" aria-orientation="horizontal">
      {tabs.map((tab, index) => (
        <a key={tab.id} href={routeHref({section:tab.id as Section})} role="tab" id={`drift-tab-${tab.id}`}
          aria-controls={`drift-panel-${tab.id}`} aria-selected={selected === tab.id}
          tabIndex={selected === tab.id ? 0 : -1}
          ref={button => { buttons.current[index] = button; }}
          className={selected === tab.id ? "tab active" : "tab"}
          onClick={event => { if(event.button===0&&!event.ctrlKey&&!event.metaKey&&!event.shiftKey&&!event.altKey) {event.preventDefault();onSelect(tab.id);} }} onKeyDown={event => navigate(event, index)}>{tab.label}</a>
      ))}
    </nav>
    </>
  );
}
