/** Preact + htm in one place: components import `html` and the hooks from here. */
import { Fragment, createContext, h, render } from "preact";
import htm from "htm";

export const html = htm.bind(h);
export { Fragment, createContext, render };
export {
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "preact/hooks";
