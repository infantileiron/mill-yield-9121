import {statuses} from '../../constants/enums.js';
import {esc} from '../../utils/format.js';
export const badge=status=>`<span class="badge ${esc(status)}">${esc(statuses[status]||status)}</span>`;
