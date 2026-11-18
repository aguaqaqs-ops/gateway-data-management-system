import { useEffect, useMemo, useState } from "react";
import {
  BrowseCommandRuntime,
  decodeBrowseState,
  type BrowseState,
} from "../../features/view-model/commands";

export function useBrowseRuntime() {
  const runtime = useMemo(
    () => new BrowseCommandRuntime(decodeBrowseState(window.location.search)),
    [],
  );
  const [browse, setBrowse] = useState<BrowseState>(runtime.snapshot.state);
  const [search, setSearch] = useState(runtime.snapshot.state.search);
  const [onlyInteresting, setOnlyInteresting] = useState(runtime.snapshot.state.onlyInteresting);
  const [debug, setDebug] = useState(runtime.snapshot.state.debug);

  useEffect(() => {
    const unsubscribe = runtime.subscribe(({ state }) => {
      setBrowse(state);
      setSearch(state.search);
      setOnlyInteresting(state.onlyInteresting);
      setDebug(state.debug);
    });
    const restore = () => runtime.restoreFromUrl();
    window.addEventListener("popstate", restore);
    return () => {
      unsubscribe();
      window.removeEventListener("popstate", restore);
    };
  }, [runtime]);

  return { runtime, browse, search, onlyInteresting, debug };
}
