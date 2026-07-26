import NotFound from '@/pages/404'
import Login from '@/pages/login'
import CustomerPortal from '@/pages/portal'
import SupportOps from '@/pages/supportops'
import {
  Navigate,
  Outlet,
  RouteObject,
  createBrowserRouter,
  useLocation,
} from 'react-router-dom'
import { RouterGuard } from './guard'

export type IRouteObject = {
  children?: IRouteObject[]
  name?: string
  auth?: boolean
  pure?: boolean
  meta?: any
} & Omit<RouteObject, 'children'>

export const routes: IRouteObject[] = [
  {
    path: '/',
    element: <Navigate to="/supportops" replace />,
  },
  {
    path: '/supportops',
    Component: SupportOps,
  },
  {
    path: '/portal',
    Component: CustomerPortal,
  },
]

function Layout() {
  const location = useLocation()
  return (
    <RouterGuard>
      <Outlet key={location.pathname} />
    </RouterGuard>
  )
}

export const router = createBrowserRouter(
  [
    helper({
      path: '/',
      Component: Layout,
      children: routes,
    }),
    helper({
      path: '/login',
      Component: Login,
      auth: false,
    }),
    helper({
      path: '404',
      Component: NotFound,
      pure: true,
    }),
    helper({
      path: '*',
      Component: NotFound,
    }),
  ],
  {
    basename: import.meta.env.BASE_URL,
  },
)

function helper(route: IRouteObject) {
  const _route = {
    ...route,
  }

  if (_route.children) {
    _route.children = _route.children.map((child: any) => helper(child))
  }

  if (_route.auth === undefined) {
    _route.auth = true
  }

  return _route as RouteObject
}
