import {batches,inspections,reviews} from '../api/business.js';
export const state={user:null,batches:[],inspections:[],reviews:[],selected:null};
export async function refresh(){[state.batches,state.inspections,state.reviews]=await Promise.all([batches.list(),inspections.list(),reviews.list()]);if(state.selected)state.selected=await reviews.get(state.selected.id);}
