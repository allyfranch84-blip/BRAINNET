import React from "react";
import { motion } from "framer-motion";

export default function SendStopButton({ processing, stopping, onStop, children, style, ...props }) {
  return <motion.button {...props} type={processing ? "button" : "submit"}
    aria-label={processing ? "Parar execução" : "Enviar"} disabled={stopping}
    onClick={processing ? onStop : undefined}
    style={processing ? { ...style, color: "#f87171", background: "rgba(239,68,68,0.12)", boxShadow: "0 0 16px rgba(239,68,68,0.20)" } : style}>
    {processing ? <span aria-hidden="true" className="h-3.5 w-3.5 rounded-sm bg-current" /> : children}
  </motion.button>;
}
