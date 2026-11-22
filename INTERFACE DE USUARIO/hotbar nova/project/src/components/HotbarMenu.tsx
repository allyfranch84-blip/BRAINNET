import { useState, type FormEvent } from 'react';
import { ChevronDown, Plus, Trash2 } from 'lucide-react';
import {
  HOTBAR_ICONS,
  MAX_CUSTOM_BUTTONS,
  MAX_CUSTOM_LABEL_LENGTH,
  SNAP_OPTIONS,
  type CustomButton,
  type HotbarIconKey,
  type MenuPlacement,
  type SnapState,
} from '@/components/hotbarConfig';

type HotbarMenuProps = {
  open: boolean;
  placement: MenuPlacement;
  snapState: SnapState;
  onSnapChange: (value: SnapState) => void;
  customButtons: CustomButton[];
  onCreate: (label: string, iconKey: HotbarIconKey) => void;
  onRemove: (id: string) => void;
};

const ICON_KEYS = Object.keys(HOTBAR_ICONS) as HotbarIconKey[];

const PLACEMENT_CLASS: Record<MenuPlacement, string> = {
  above: 'bottom-full right-0 origin-bottom-right pb-3',
  left: 'right-full top-1/2 origin-right -translate-y-1/2 pr-3',
  right: 'left-full top-1/2 origin-left -translate-y-1/2 pl-3',
};

export default function HotbarMenu({ open, placement, snapState, onSnapChange, customButtons, onCreate, onRemove }: HotbarMenuProps) {
  const [addOpen, setAddOpen] = useState(false);
  const [label, setLabel] = useState('');
  const [iconKey, setIconKey] = useState<HotbarIconKey>('zap');

  const isFull = customButtons.length >= MAX_CUSTOM_BUTTONS;
  const canCreate = label.trim().length > 0 && !isFull;

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!canCreate) return;
    onCreate(label.trim(), iconKey);
    setLabel('');
    setAddOpen(false);
  };

  return (
    <div className={`app-no-drag absolute transition-[opacity,transform,visibility] duration-300 ease-out ${PLACEMENT_CLASS[placement]} ${open ? 'scale-100 opacity-100' : 'pointer-events-none invisible scale-95 opacity-0'}`}>
      <div className="w-[340px] max-w-[calc(100vw-32px)] rounded-2xl border border-white/10 bg-[#0d0d14]/90 p-2 shadow-[0_24px_60px_-12px_rgba(0,0,0,0.9),0_0_24px_rgba(127,240,224,0.12)] backdrop-blur-2xl">
        <p className="px-3 pb-2 pt-1 font-mono text-[9px] uppercase tracking-[0.25em] text-gray-400">Funções</p>

        <button type="button" onClick={() => setAddOpen((value) => !value)} aria-expanded={addOpen} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors hover:bg-white/5 focus-visible:bg-white/5 focus-visible:outline-none">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#7ff0e0]/10 text-[#7ff0e0]">
            <Plus size={16} strokeWidth={2.25} />
          </span>
          <span className="flex-1">
            <span className="block text-sm font-medium text-gray-100">Adicionar botão</span>
            <span className="block text-xs text-gray-400">Crie uma função para a barra</span>
          </span>
          <ChevronDown size={16} className={`text-gray-400 transition-transform duration-300 ${addOpen ? 'rotate-180' : ''}`} />
        </button>

        <div className={`grid transition-[grid-template-rows,opacity] duration-300 ease-out ${addOpen ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0'}`}>
          <div className="overflow-hidden">
            <form onSubmit={handleSubmit} className="space-y-3 px-3 pb-3 pt-2">
              <input value={label} onChange={(e) => setLabel(e.target.value)} maxLength={MAX_CUSTOM_LABEL_LENGTH} placeholder="Nome (até 8 letras)" aria-label="Nome do botão" className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 font-mono text-xs uppercase tracking-widest text-gray-100 outline-none placeholder:normal-case placeholder:tracking-normal placeholder:text-gray-500 focus:border-[#7ff0e0]/50" />
              <div className="grid grid-cols-8 gap-1.5">
                {ICON_KEYS.map((key) => {
                  const Icon = HOTBAR_ICONS[key];
                  const selected = key === iconKey;
                  return (
                    <button key={key} type="button" onClick={() => setIconKey(key)} aria-pressed={selected} aria-label={`Ícone ${key}`} className={`flex h-8 items-center justify-center rounded-lg border transition-colors ${selected ? 'border-[#7ff0e0]/60 bg-[#7ff0e0]/10 text-[#7ff0e0]' : 'border-white/10 text-gray-400 hover:text-gray-100'}`}>
                      <Icon size={14} strokeWidth={2.25} />
                    </button>
                  );
                })}
              </div>
              <p className="font-mono text-[10px] leading-relaxed text-gray-400">{isFull ? `Limite de ${MAX_CUSTOM_BUTTONS} botões atingido.` : 'A função ainda não foi definida. O botão aparece na barra.'}</p>
              <button type="submit" disabled={!canCreate} className="w-full rounded-lg bg-[#7ff0e0] py-2 font-mono text-xs uppercase tracking-widest text-[#0d0d14] transition-opacity hover:opacity-90 disabled:opacity-40">Criar botão</button>
            </form>
          </div>
        </div>

        <div className="my-1 h-px bg-white/10" />
        <p className="px-3 pb-2 pt-2 font-mono text-[9px] uppercase tracking-[0.25em] text-gray-400">Posição</p>
        <div className="grid grid-cols-4 gap-1 rounded-xl bg-white/5 p-1">
          {SNAP_OPTIONS.map(({ value, label: optionLabel, Icon }) => {
            const selected = value === snapState;
            return (
              <button key={value} type="button" onClick={() => onSnapChange(value)} aria-pressed={selected} className={`flex flex-col items-center gap-1 rounded-lg py-2 transition-colors ${selected ? 'bg-[#7ff0e0]/15 text-[#7ff0e0]' : 'text-gray-400 hover:text-gray-100'}`}>
                <Icon size={14} strokeWidth={2.25} />
                <span className="font-mono text-[8px] uppercase tracking-widest">{optionLabel}</span>
              </button>
            );
          })}
        </div>

        <div className="my-1 h-px bg-white/10" />
        <p className="px-3 pb-1 pt-2 font-mono text-[9px] uppercase tracking-[0.25em] text-gray-400">Na barra</p>
        {customButtons.length === 0 ? (
          <p className="px-3 py-2 text-xs text-gray-400">Nenhum botão personalizado</p>
        ) : (
          <ul className="space-y-0.5">
            {customButtons.map((button) => {
              const Icon = HOTBAR_ICONS[button.iconKey];
              return (
                <li key={button.id} className="flex items-center gap-3 rounded-xl px-3 py-2 transition-colors hover:bg-white/5">
                  <Icon size={14} strokeWidth={2.25} className="shrink-0 text-gray-300" />
                  <span className="flex-1 font-mono text-xs uppercase tracking-widest text-gray-100">{button.label}</span>
                  <button type="button" onClick={() => onRemove(button.id)} aria-label={`Remover ${button.label}`} className="rounded-md p-1 text-gray-400 transition-colors hover:text-red-500">
                    <Trash2 size={14} strokeWidth={2.25} />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
