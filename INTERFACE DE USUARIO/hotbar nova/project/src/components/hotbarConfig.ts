import {
  Zap,
  Star,
  Folder,
  Terminal,
  Brain,
  Globe,
  Bookmark,
  Cpu,
  CircleDot,
  PanelBottom,
  PanelLeft,
  PanelRight,
  type LucideIcon,
} from 'lucide-react';

export const HOTBAR_ICONS = {
  zap: Zap,
  star: Star,
  folder: Folder,
  terminal: Terminal,
  brain: Brain,
  globe: Globe,
  bookmark: Bookmark,
  cpu: Cpu,
} satisfies Record<string, LucideIcon>;

export type HotbarIconKey = keyof typeof HOTBAR_ICONS;

export type CustomButton = {
  id: string;
  label: string;
  iconKey: HotbarIconKey;
};

export const MAX_CUSTOM_BUTTONS = 4;
export const MAX_CUSTOM_LABEL_LENGTH = 8;

export type SnapState = 'floating' | 'bottom' | 'left' | 'right';

export const SNAP_OPTIONS: { value: SnapState; label: string; Icon: LucideIcon }[] = [
  { value: 'floating', label: 'Flutuante', Icon: CircleDot },
  { value: 'bottom', label: 'Base', Icon: PanelBottom },
  { value: 'left', label: 'Esquerda', Icon: PanelLeft },
  { value: 'right', label: 'Direita', Icon: PanelRight },
];

export type MenuPlacement = 'above' | 'left' | 'right';
