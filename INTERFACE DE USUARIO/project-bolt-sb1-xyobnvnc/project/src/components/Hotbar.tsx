import { motion, type Variants } from 'framer-motion';
import { Mic, Search, Maximize2, X } from 'lucide-react';

type HotbarProps = {
  isMicActive?: boolean;
  onMic?: () => void;
  onSearch?: () => void;
  onExpand?: () => void;
  onClose?: () => void;
};

const SPRING = { type: 'spring', stiffness: 300, damping: 25 } as const;

const pillVariants: Variants = {
  rest: { width: 480, transition: SPRING },
  hover: { width: 700, transition: SPRING },
};

const buttonVariants: Variants = {
  rest: { scale: 1, y: 0 },
  hover: { scale: 1.15, y: -2 },
};

function Equalizer() {
  const bars = [0, 1, 2, 3];
  return (
    <div className="flex h-5 items-end gap-[2px] overflow-hidden">
      {bars.map((i) => (
        <motion.span
          key={i}
          className="w-[2px] rounded-full bg-[#7ff0e0]"
          style={{ boxShadow: '0 0 6px rgba(127,240,224,0.8)' }}
          animate={{ height: ['20%', '100%', '35%', '80%', '20%'] }}
          transition={{
            repeat: Infinity,
            duration: 1,
            ease: 'easeInOut',
            delay: i * 0.12,
          }}
        />
      ))}
    </div>
  );
}

type PillButtonProps = {
  label: string;
  active?: boolean;
  accent: string; // tailwind text color class on hover/active
  onClick?: () => void;
  children: React.ReactNode;
};

function PillButton({ label, active, accent, onClick, children }: PillButtonProps) {
  return (
    <motion.button
      type="button"
      onClick={onClick}
      variants={buttonVariants}
      initial="rest"
      whileHover="hover"
      transition={{ type: 'spring', stiffness: 400, damping: 12 }}
      className="group relative flex flex-col items-center justify-center gap-1 outline-none"
    >
      {/* progress ring */}
      <span
        className={`pointer-events-none absolute -inset-2 rounded-full border transition-colors duration-300 ${
          active
            ? 'border-[#7ff0e0]/60 opacity-100'
            : 'border-transparent opacity-0 group-hover:border-white/20 group-hover:opacity-100'
        }`}
        style={
          active
            ? { boxShadow: '0 0 12px rgba(127,240,224,0.35)' }
            : undefined
        }
      />
      <span
        className={`flex h-7 items-center justify-center text-gray-400 transition-colors duration-300 group-hover:${accent} ${
          active ? accent : ''
        }`}
      >
        {children}
      </span>
      <span
        className={`font-mono text-[8px] uppercase leading-none tracking-widest text-gray-500 transition-colors duration-300 group-hover:text-gray-300 ${
          active ? 'text-gray-200' : ''
        }`}
      >
        {label}
      </span>
    </motion.button>
  );
}

export default function Hotbar({
  isMicActive = false,
  onMic,
  onSearch,
  onExpand,
  onClose,
}: HotbarProps) {
  return (
    <div className="pointer-events-none fixed inset-0 z-50 flex items-end justify-center pb-5">
      <motion.div
        initial={{ y: 50, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ type: 'spring', stiffness: 260, damping: 22, delay: 0.15 }}
        className="pointer-events-auto"
      >
        <motion.div
          variants={pillVariants}
          initial="rest"
          whileHover="hover"
          className="flex h-16 items-center justify-around rounded-full border border-white/15 bg-[#0d0d14]/80 px-6 font-mono backdrop-blur-2xl"
          style={{
            boxShadow:
              '0 0 20px rgba(127,240,224,0.2), 0 20px 50px -10px rgba(0,0,0,0.8), inset 0 1px 0 0 rgba(255,255,255,0.05)',
          }}
        >
          {/* MIC */}
          <PillButton
            label="MIC"
            active={isMicActive}
            accent="text-[#7ff0e0]"
            onClick={onMic}
          >
            <div className="flex items-center gap-2">
              <Mic
                size={18}
                strokeWidth={2.25}
                style={
                  isMicActive
                    ? { filter: 'drop-shadow(0 0 6px rgba(127,240,224,0.9))' }
                    : undefined
                }
              />
              {isMicActive && <Equalizer />}
            </div>
          </PillButton>

          <Divider />

          {/* SEARCH */}
          <PillButton
            label="BUSCAR"
            accent="text-violet-400"
            onClick={onSearch}
          >
            <Search size={18} strokeWidth={2.25} />
          </PillButton>

          <Divider />

          {/* EXPAND */}
          <PillButton
            label="GUI"
            accent="text-[#7ff0e0]"
            onClick={onExpand}
          >
            <Maximize2 size={18} strokeWidth={2.25} />
          </PillButton>

          <Divider />

          {/* CLOSE */}
          <PillButton label="SAIR" accent="text-red-500" onClick={onClose}>
            <X size={18} strokeWidth={2.25} />
          </PillButton>
        </motion.div>
      </motion.div>
    </div>
  );
}

function Divider() {
  return (
    <span className="h-8 w-px shrink-0 bg-white/10" aria-hidden />
  );
}
