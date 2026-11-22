import { motion } from 'framer-motion';
import { Mic, Search, Maximize2, X } from 'lucide-react';

const SPRING = { type: 'spring', stiffness: 300, damping: 25 };
const pillVariants = {
  rest: { width: 480, transition: SPRING },
  hover: { width: 700, transition: SPRING },
};
const buttonVariants = {
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
          transition={{ repeat: Infinity, duration: 1, ease: 'easeInOut', delay: i * 0.12 }}
        />
      ))}
    </div>
  );
}

function PillButton({ label, active, accent, onClick, children }) {
  return (
    <motion.button
      type="button"
      onClick={onClick}
      variants={buttonVariants}
      initial="rest"
      whileHover="hover"
      transition={{ type: 'spring', stiffness: 400, damping: 12 }}
      className="group relative flex h-8 w-8 items-center justify-center rounded-full outline-none"
      aria-label={label}
      title={label}
      style={{ WebkitAppRegion: "no-drag" }}
    >
      <span
        className={`pointer-events-none absolute -inset-2 rounded-full border transition-colors duration-300 ${
          active ? 'border-[#7ff0e0]/60 opacity-100' : 'border-transparent opacity-0 group-hover:border-white/20 group-hover:opacity-100'
        }`}
        style={active ? { boxShadow: '0 0 12px rgba(127,240,224,0.35)' } : undefined}
      />
      <span className={`flex items-center justify-center text-gray-400 transition-colors duration-300 ${accent} ${active ? accent : ''}`}>
        {children}
      </span>
    </motion.button>
  );
}

function Divider() {
  return <span className="h-8 w-px shrink-0 bg-white/10" aria-hidden />;
}

export default function Hotbar({ isMicActive = false, onMic, onSearch, onExpand, onClose }) {
  return (
    <div
      className="flex h-full w-full items-center justify-center gap-24 bg-[#0d0d14] px-8 font-mono shadow-2xl"
      style={{ WebkitAppRegion: "drag" }}
    >
          <PillButton label="MIC" active={isMicActive} accent="text-[#7ff0e0]" onClick={onMic}>
            <div className="flex items-center gap-2">
              <Mic size={18} strokeWidth={2.25} style={isMicActive ? { filter: 'drop-shadow(0 0 6px rgba(127,240,224,0.9))' } : undefined} />
              {isMicActive && <Equalizer />}
            </div>
          </PillButton>
          <PillButton label="BUSCAR" accent="text-violet-400" onClick={onSearch}>
            <Search size={18} strokeWidth={2.25} />
          </PillButton>
          <PillButton label="GUI" accent="text-[#7ff0e0]" onClick={onExpand}>
            <Maximize2 size={18} strokeWidth={2.25} />
          </PillButton>
          <PillButton label="SAIR" accent="text-red-500" onClick={onClose}>
            <X size={18} strokeWidth={2.25} />
          </PillButton>
    </div>
  );
}