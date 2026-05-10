type AMapMapOptions = {
  center?: [number, number];
  zoom?: number;
  viewMode?: "2D" | "3D";
};

export type AMapOverlayInstance = {
  setMap: (map: AMapMapInstance | null) => void;
};

export type AMapMapInstance = {
  destroy: () => void;
  setFitView: (overlays?: AMapOverlayInstance[]) => void;
};

type AMapMarkerOptions = {
  map?: AMapMapInstance;
  position: [number, number];
  title?: string;
  content?: string | HTMLElement;
};

type AMapPolylineOptions = {
  map?: AMapMapInstance;
  path: [number, number][];
  strokeColor?: string;
  strokeOpacity?: number;
  strokeWeight?: number;
  lineJoin?: "miter" | "round" | "bevel";
  zIndex?: number;
};

export type AMapMarkerInstance = AMapOverlayInstance & {
  on: (eventName: "click", handler: () => void) => void;
};

export type AMapPolylineInstance = AMapOverlayInstance;

type AMapMarkerConstructor = new (
  options: AMapMarkerOptions,
) => AMapMarkerInstance;

type AMapPolylineConstructor = new (
  options: AMapPolylineOptions,
) => AMapPolylineInstance;

type AMapMapConstructor = new (
  container: HTMLElement,
  options: AMapMapOptions,
) => AMapMapInstance;

export type AMapConstructorNamespace = {
  Map: AMapMapConstructor;
  Marker: AMapMarkerConstructor;
  Polyline: AMapPolylineConstructor;
};

export type AMapNamespace = AMapConstructorNamespace;

declare global {
  interface Window {
    AMap?: AMapNamespace;
    _AMapSecurityConfig?: {
      securityJsCode?: string;
    };
    __amapLoaderPromise?: Promise<AMapNamespace>;
  }
}

type LoadAmapOptions = {
  jsKey: string;
  securityJsCode: string;
};

const AMAP_SCRIPT_ID = "amap-js-api-v2";

export function loadAmap({ jsKey, securityJsCode }: LoadAmapOptions) {
  if (typeof window === "undefined") {
    return Promise.reject(new Error("AMap can only be loaded in the browser."));
  }

  if (window.AMap) {
    return Promise.resolve(window.AMap);
  }

  if (window.__amapLoaderPromise) {
    return window.__amapLoaderPromise;
  }

  window._AMapSecurityConfig = {
    securityJsCode,
  };

  window.__amapLoaderPromise = new Promise<AMapNamespace>((resolve, reject) => {
    const existingScript = document.getElementById(AMAP_SCRIPT_ID);
    if (existingScript) {
      existingScript.addEventListener("load", () => {
        if (window.AMap) {
          resolve(window.AMap);
        } else {
          reject(new Error("AMap script loaded but window.AMap is unavailable."));
        }
      });
      existingScript.addEventListener("error", () => {
        reject(new Error("Failed to load AMap JS API."));
      });
      return;
    }

    const script = document.createElement("script");
    script.id = AMAP_SCRIPT_ID;
    script.async = true;
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(jsKey)}`;
    script.onload = () => {
      if (window.AMap) {
        resolve(window.AMap);
        return;
      }

      reject(new Error("AMap script loaded but window.AMap is unavailable."));
    };
    script.onerror = () => {
      reject(new Error("Failed to load AMap JS API."));
    };

    document.head.appendChild(script);
  });

  return window.__amapLoaderPromise;
}
