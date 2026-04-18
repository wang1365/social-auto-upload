import { createRouter, createWebHashHistory } from 'vue-router'
import Dashboard from '../views/Dashboard.vue'
import AccountManagement from '../views/AccountManagement.vue'
import MaterialManagement from '../views/MaterialManagement.vue'
import DownloadCenter from '../views/DownloadCenter.vue'
import PublishCenter from '../views/PublishCenter.vue'
import About from '../views/About.vue'
import SystemSettings from '../views/SystemSettings.vue'

const routes = [
  {
    path: '/',
    name: 'Dashboard',
    component: Dashboard
  },
  {
    path: '/account-management',
    name: 'AccountManagement',
    component: AccountManagement
  },
  {
    path: '/material-management',
    name: 'MaterialManagement',
    component: MaterialManagement
  },
  {
    path: '/download-center',
    name: 'DownloadCenter',
    component: DownloadCenter
  },
  {
    path: '/publish-center',
    name: 'PublishCenter',
    component: PublishCenter
  },
  {
    path: '/about',
    name: 'About',
    component: About
  },
  {
    path: '/system-settings',
    name: 'SystemSettings',
    component: SystemSettings
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

export default router
