export function route(){const page=location.hash.slice(1)||'batches';return ['batches','inspections','diagnosis','reports'].includes(page)?page:'batches';}
