import { index, route, type RouteConfig } from '@react-router/dev/routes'

export default [
  index('./routes/home.tsx'),
  route('game/:slug', './routes/game.tsx'),
  route('best/games/:year', './routes/year.tsx'),
  route('best/:collection', './routes/curated.tsx'),
  route('deals', './routes/deals.tsx'),
  route('login', './routes/login.tsx'),
  route('register', './routes/register.tsx'),
  route('forgot-password', './routes/forgot-password.tsx'),
  route('reset-password', './routes/reset-password.tsx'),
  route('verify-email', './routes/verify-email.tsx'),
  route('unsubscribe', './routes/unsubscribe.tsx'),
  route('account', './routes/account.tsx'),
  route('alerts', './routes/alerts.tsx'),
  route('settings', './routes/settings.tsx'),
  route('about', './routes/about.tsx'),
  route('admin', './routes/admin.tsx'),
  route('*', './routes/not-found.tsx'),
] satisfies RouteConfig
