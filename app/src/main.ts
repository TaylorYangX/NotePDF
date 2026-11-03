import { createApp } from 'vue'
import App from './App.vue'
import { initApi } from './api'
import { i18n } from './i18n'
import { startApp, store } from './store'
import './style.css'

createApp(App).use(i18n).mount('#app')
initApi()
  .then(startApp)
  .catch((e) => (store.loadError = String(e)))
