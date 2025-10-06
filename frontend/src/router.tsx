import { createBrowserRouter, Navigate } from "react-router-dom";

import { AppLayout } from "./components/AppLayout";
import { AuthoringPage } from "./pages/AuthoringPage";
import { AuthPage } from "./pages/AuthPage";
import { HistoryPage } from "./pages/HistoryPage";
import { ReviewPage } from "./pages/ReviewPage";
import { ReviewDetailPage } from "./pages/ReviewDetailPage";
import { SearchPage } from "./pages/SearchPage";
import { NoteDetailPage } from "./pages/NoteDetailPage";
import { HomePage } from "./pages/HomePage";

const BASE_PATH = "/knowledge";

export const router = createBrowserRouter(
  [
    {
      path: "/auth",
      element: <AuthPage />
    },
    {
      path: "/",
      element: <AppLayout />,
      children: [
        { index: true, element: <HomePage /> },
        { path: "search", element: <SearchPage /> },
        { path: "note/:noteId", element: <NoteDetailPage /> },
        { path: "note/:noteId/history", element: <HistoryPage /> },
        { path: "review", element: <ReviewPage /> },
        { path: "review/:reviewId", element: <ReviewDetailPage /> },
        { path: "edit/new", element: <AuthoringPage /> },
        { path: "edit/:noteId", element: <AuthoringPage /> },
        { path: "author", element: <Navigate to="/edit/new" replace /> }
      ]
    },
    { path: "*", element: <Navigate to="/" replace /> }
  ],
  {
    basename: BASE_PATH
  }
);
