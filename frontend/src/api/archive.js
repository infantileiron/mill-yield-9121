import {api,post} from './client.js';
export const archives={list:()=>api('/archives'),detail:m=>api('/archives/'+m),start:m=>post('/archives',{month:m}),restore:m=>post('/archives/'+m+'/restore',{}),verify:m=>post('/archives/'+m+'/verify',{})};
