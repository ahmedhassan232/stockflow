import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { SessionBootstrap } from "@/features/auth/guards";
import { AppProviders } from "./providers";
import { routes } from "./routes";

const router = createBrowserRouter(routes);

export function App() {
  return (
    <AppProviders>
      <SessionBootstrap>
        <RouterProvider router={router} />
      </SessionBootstrap>
    </AppProviders>
  );
}
