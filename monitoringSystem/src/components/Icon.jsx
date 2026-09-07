const paths = {
  leaf: <><path d="M19.5 4.5C11 4.8 6.2 8.7 5.4 15.6c-.3 2.7 1.6 4.6 4.2 4.1 6.2-1.1 9.7-6 9.9-15.2Z"/><path d="M4 21c2.4-5.4 6.3-8.7 11.4-10.8"/></>,
  home: <path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z"/>,
  bin: <><path d="M5 7h14l-1 14H6L5 7Z"/><path d="M4 7h16M9 7V4h6v3M9 11v6M15 11v6"/></>,
  device: <><rect x="5" y="3" width="14" height="18" rx="3"/><path d="M9 7h6M10 17h4"/></>,
  plus: <path d="M12 5v14M5 12h14"/>,
  menu: <path d="M4 7h16M4 12h16M4 17h16"/>,
  bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/></>,
  temp: <><path d="M14 14.8V5a4 4 0 0 0-8 0v9.8a6 6 0 1 0 8 0Z"/><path d="M10 5v11"/></>,
  drop: <path d="M12 2S5 10 5 15a7 7 0 0 0 14 0c0-5-7-13-7-13Z"/>,
  wind: <path d="M4 8h10a3 3 0 1 0-3-3M4 12h15a3 3 0 1 1-3 3M4 16h7"/>,
  activity: <path d="M3 12h4l2-7 4 14 2-7h6"/>,
  flame: <><path d="M12 22c4 0 7-3 7-7 0-5-4-9-7-13 0 5-7 7-7 13 0 4 3 7 7 7Z"/><path d="M9.5 18c0-2 1.7-3.4 2.5-5 .8 1.6 2.5 3 2.5 5"/></>,
  arrow: <path d="M5 12h14M13 6l6 6-6 6"/>,
  check: <path d="m5 12 4 4L19 6"/>,
  clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
  settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3A1.7 1.7 0 0 0 10 3v-.2h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z"/></>,
};

export function Icon({ name, size, className = "" }) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {paths[name] ?? paths.activity}
    </svg>
  );
}
