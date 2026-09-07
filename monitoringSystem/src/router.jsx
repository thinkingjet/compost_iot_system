import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

const RouterContext = createContext(null);
const getPath = () => location.pathname || "/setup/device";

export function RouterProvider({ children }) {
  const [pathname, setPathname] = useState(getPath);
  useEffect(() => {
    const handleChange = () => setPathname(getPath());
    addEventListener("popstate", handleChange);
    return () => removeEventListener("popstate", handleChange);
  }, []);
  const navigate = useCallback((to) => {
    if (getPath() !== to) history.pushState({}, "", to);
    setPathname(to);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);
  const value = useMemo(() => ({ pathname, navigate }), [pathname, navigate]);
  return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>;
}

export function useLocation() {
  const { pathname } = useContext(RouterContext);
  return { pathname };
}

export function useNavigate() {
  return useContext(RouterContext).navigate;
}

export function useParams() {
  const { pathname } = useContext(RouterContext);
  const [, type, tab] = pathname.split("/");
  return { type, tab };
}

export function NavLink({ to, className, onClick, children }) {
  const { pathname, navigate } = useContext(RouterContext);
  const isActive = pathname === to || (to === "/bins" && pathname.startsWith("/bin/")) || (to === "/devices" && pathname.startsWith("/device/"));
  return <a href={to} className={typeof className === "function" ? className({ isActive }) : className} onClick={(event) => { event.preventDefault(); onClick?.(event); navigate(to); }}>{children}</a>;
}
