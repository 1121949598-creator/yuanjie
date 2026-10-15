import { createApp } from "vue";
import { createRouter, createWebHashHistory } from "vue-router";
import App from "./App.vue";
import Welcome from "./pages/Welcome.vue";
import Upload from "./pages/Upload.vue";
import History from "./pages/History.vue";
import Scan from "./pages/Scan.vue";
import MascotGallery from "./pages/MascotGallery.vue";
import Entry from './pages/Entry.vue';
import Examples from './pages/Examples.vue';
import { journeyKey } from './journeys';
import "./style.css";
const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: "/", component: Welcome },
    { path: '/entry', component: Entry },
    { path: "/new", component: Upload, beforeEnter: to => to.query.examples ? {path: '/examples', query: {mode: journeyKey(to.query.mode)}} : true },
    { path: '/examples', component: Examples },
    { path: "/history", component: History },
    { path: "/mascot", component: MascotGallery },
    { path: "/scan/:id/:section?", component: Scan },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
  scrollBehavior: () => ({ top: 0 }),
});
createApp(App).use(router).mount("#app");
