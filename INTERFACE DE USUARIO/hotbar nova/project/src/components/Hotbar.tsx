import { useState, useEffect, Fragment, type ReactNode } from 'react';
import { Mic, Search, Maximize2, X, Plus } from 'lucide-react';
import HotbarMenu from '@/components/HotbarMenu';
import {
  HOTBAR_ICONS,
  MAX_CUSTOM_BUTTONS,
  type CustomButton,
  type HotbarIconKey,
  type MenuPlacement,
  type SnapState,
} from '@/components/hotbarConfig';

type HotbarProps = {
  isMicActive?: boolean;
  onMic?: () => void;
  onSearch?: () => void;
  onExpand?: () => void;
  onClose?: () => void;
};

type HotbarItemProps = {
  label: string;
  hoverClass: string;
  vertical: boolean;
  onClick?: () => void;
  active?: boolean;
  children: ReactNode;
};

const EQ_DURATIONS = ['0.9s', '1.1s', '0.8s', '1.0s'];

const WRAPPER_POSITION: Record<SnapState, string> = {
  floating: 'inset-x-0 bottom-0 justify-center pb-5',
  bottom: 'inset-x-0 bottom-0 justify-center',
  left: 'inset-y-0 left-0 items-center',
  right: 'inset-y-0 right-0 items-center justify-end',
};

const PILL_OPEN_SIZE: Record<SnapState, string> = {
  floating: 'h-[30px] w-[950px] max-w-[calc(100vw-32px)] rounded-full',
  bottom: 'h-[30px] w-[950px] max-w-[calc(100vw-32px)] rounded-t-full rounded-b-none',
  left: 'h-[min(560px,calc(100vh-32px))] w-[56px] rounded-l-none rounded-r-full',
  right: 'h-[min(560px,calc(100vh-32px))] w-[56px] rounded-r-none rounded-l-full',
};

const MENU_PLACEMENT: Record<SnapState, MenuPlacement> = {
  floating: 'above',
  bottom: 'above',
  left: 'right',
  right: 'left',
};

function HotbarItem({ label, hoverClass, vertical, onClick, active = false, children }: HotbarItemProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={vertical ? label : undefined}
      className={`app-no-drag group flex items-center rounded-full outline-none transition-all duration-300 ease-out hover:-translate-y-0.5 hover:scale-[1.15] focus-visible:ring-1 focus-visible:ring-white/40 motion-reduce:transform-none ${
        vertical ? 'w-full flex-col gap-1 py-2' : 'h-full gap-1.5 px-2'
      } ${active ? 'text-[#7ff0e0]' : `text-gray-400 ${hoverClass}`}`}
    >
      {children}
      {!vertical && (
        <span className="font-mono text-[8px] uppercase leading-none tracking-widest">{label}</span>
      )}
    </button>
  );
}

function Equalizer() {
  return (
    <span className="flex h-3 items-end gap-[2px]" aria-hidden>
      {EQ_DURATIONS.map((duration, i) => (
        <span
          key={i}
          className="eq-bar h-3 w-[2px] rounded-full bg-[#7ff0e0]"
          style={{ animationDuration: duration, animationDelay: `${i * 0.15}s` }}
        />
      ))}
    </span>
  );
}

function Divider({ vertical }: { vertical: boolean }) {
  return <span className={`shrink-0 bg-white/10 ${vertical ? 'h-px w-3' : 'h-3 w-px'}`} aria-hidden />;
}

export default function Hotbar({ isMicActive = false, onMic, onSearch, onExpand, onClose }: HotbarProps) {
  const [open, setOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [snapState, setSnapState] = useState<SnapState>('floating');
  const [customButtons, setCustomButtons] = useState<CustomButton[]>([]);

  useEffect(() => {
    const handleSnap = (e: Event) => {
      const customEvent = e as CustomEvent;
      if (customEvent.detail) setSnapState(customEvent.detail);
    };
    window.addEventListener('aios:snap', handleSnap);
    return () => window.removeEventListener('aios:snap', handleSnap);
  }, []);

  const vertical = snapState === 'left' || snapState === 'right';

  const createCustomButton = (label: string, iconKey: HotbarIconKey) => {
    setCustomButtons((current) =>
      current.length >= MAX_CUSTOM_BUTTONS ? current : [...current, { id: Date.now().toString(), label, iconKey }]
    );
  };

  const removeCustomButton = (id: string) => {
    setCustomButtons((current) => current.filter((button) => button.id !== id));
  };

  return (
    <div className={`pointer-events-none fixed z-50 flex ${WRAPPER_POSITION[snapState]}`}>
      <div
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => { setOpen(false); setMenuOpen(false); }}
        onFocus={() => setOpen(true)}
        onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) { setOpen(false); setMenuOpen(false); } }}
        className="pointer-events-auto relative"
      >
        <HotbarMenu
          open={open && menuOpen}
          placement={MENU_PLACEMENT[snapState]}
          snapState={snapState}
          onSnapChange={setSnapState}
          customButtons={customButtons}
          onCreate={createCustomButton}
          onRemove={removeCustomButton}
        />

        <div
          className={`app-drag relative border transition-[width,height,border-radius,background-color,box-shadow,border-color] duration-500 ease-[cubic-bezier(0.34,1.56,0.64,1)] motion-reduce:transition-none ${
            open
              ? `${PILL_OPEN_SIZE[snapState]} border-white/15 bg-[#0d0d14]/80 shadow-[0_0_20px_rgba(127,240,224,0.2),0_20px_50px_-10px_rgba(0,0,0,0.8)] backdrop-blur-xl`
              : 'h-[14px] w-[14px] rounded-full border-transparent bg-[#7ff0e0] shadow-[0_0_10px_3px_rgba(127,240,224,0.6),0_0_28px_rgba(127,240,224,0.35)]'
          }`}
        >
          <button
            type="button"
            aria-label="Abrir barra"
            onClick={() => setOpen(true)}
            className={`app-no-drag absolute inset-0 rounded-full outline-none transition-opacity duration-200 ${
              open ? 'pointer-events-none invisible opacity-0' : 'opacity-100'
            }`}
          />

          {open && !vertical && (
            <span
              aria-hidden
              className="brainnet-flash pointer-events-none absolute inset-0 flex items-center justify-center font-mono text-[9px] uppercase text-[#7ff0e0] drop-shadow-[0_0_6px_rgba(127,240,224,0.8)]"
            >
              BRAINNET
            </span>
          )}

          <nav
            aria-label="Barra de ferramentas"
            className={`absolute inset-0 flex items-center transition-[opacity,transform,visibility] duration-300 ease-out ${
              vertical ? 'flex-col justify-around py-4' : 'justify-around px-4'
            } ${open ? 'translate-y-0 opacity-100 delay-150' : 'pointer-events-none invisible translate-y-1 opacity-0'}`}
          >
            <HotbarItem label="MIC" hoverClass="hover:text-[#7ff0e0]" vertical={vertical} onClick={onMic} active={isMicActive}>
              <Mic size={13} strokeWidth={2.25} className={isMicActive ? 'drop-shadow-[0_0_4px_rgba(127,240,224,0.9)]' : ''} />
              {isMicActive && <Equalizer />}
            </HotbarItem>

            <Divider vertical={vertical} />

            <HotbarItem label="BUSCAR" hoverClass="hover:text-violet-400" vertical={vertical} onClick={onSearch}>
              <Search size={13} strokeWidth={2.25} />
            </HotbarItem>

            <Divider vertical={vertical} />

            <HotbarItem label="GUI" hoverClass="hover:text-[#7ff0e0]" vertical={vertical} onClick={() => { window.location.href = 'aios://expand'; }}>
              <Maximize2 size={13} strokeWidth={2.25} />
            </HotbarItem>

            {customButtons.map((button) => {
              const Icon = HOTBAR_ICONS[button.iconKey];
              return (
                <Fragment key={button.id}>
                  <Divider vertical={vertical} />
                  <HotbarItem label={button.label} hoverClass="hover:text-white" vertical={vertical}>
                    <Icon size={13} strokeWidth={2.25} />
                  </HotbarItem>
                </Fragment>
              );
            })}

            <Divider vertical={vertical} />

            <HotbarItem label="MAIS" hoverClass="hover:text-white" vertical={vertical} active={menuOpen} onClick={() => setMenuOpen((value) => !value)}>
              <Plus size={13} strokeWidth={2.25} />
            </HotbarItem>

            <Divider vertical={vertical} />

            <HotbarItem label="SAIR" hoverClass="hover:text-red-500" vertical={vertical} onClick={() => { window.location.href = 'aios://close'; }}>
              <X size={13} strokeWidth={2.25} />
            </HotbarItem>
          </nav>
        </div>
      </div>
    </div>
  );
}
