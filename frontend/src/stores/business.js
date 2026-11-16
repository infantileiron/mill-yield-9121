import {batches,inspections,reviews} from '../api/business.js';
import {archives} from '../api/archive.js';
export const state={user:null,batches:[],inspections:[],reviews:[],archives:[],archiveDetail:null,selected:null};
export async function refresh(){[state.batches,state.inspections,state.reviews,state.archives]=await Promise.all([batches.list(),inspections.list(),reviews.list(),archives.list()]);if(state.selected)state.selected=await reviews.get(state.selected.id);if(state.archiveDetail)state.archiveDetail=await archives.detail(state.archiveDetail.month);}
