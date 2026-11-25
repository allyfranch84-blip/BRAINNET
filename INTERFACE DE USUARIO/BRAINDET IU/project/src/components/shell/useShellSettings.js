
import {useState, useEffect, useCallback} from "react";
import {THEMES, validTheme, isLightTheme} from "./themes";

function read(key, fallback) {
  try {
    return localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}

function save(key, value) {
  try { localStorage.setItem(key, value); } catch {}
}

export function useShellSettings(kernel) {
  const [theme, setTheme] = useState(
    () => validTheme(read("brainnet_theme", "dark"))
  );

  const [lite, setLite] = useState(
    () => read("brainnet_lite", "1") !== "0"
  );

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = isLightTheme(theme) ? "light" : "dark";
    root.dataset.palette = theme;
    root.dataset.shellLite = lite ? "1" : "0";

    Object.entries(THEMES[theme]).forEach(([key, value]) => {
      root.style.setProperty(key, value);
    });

    save("brainnet_theme", theme);
    save("brainnet_lite", lite ? "1" : "0");
  }, [theme, lite]);

  const chooseTheme = useCallback(value => {
    if (!Object.hasOwn(THEMES, value)) return;
    setTheme(value);
    kernel.call("set_theme", value);
  }, [kernel.call]);

  const toggleTheme = useCallback(value => {
    if (typeof value === "string") {
      chooseTheme(value);
      return;
    }

    const keys = Object.keys(THEMES);
    chooseTheme(keys[(keys.indexOf(theme) + 1) % keys.length]);
  }, [theme, chooseTheme]);

  return {theme, toggleTheme, lite, setLite};
}
