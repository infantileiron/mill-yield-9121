export function formData(form,numeric=[]){const out=Object.fromEntries(new FormData(form));for(const k of numeric)out[k]=Number(out[k]);return out;}
export function notify(message,error=false){const el=document.getElementById('notice');if(!el)return;el.textContent=message;el.className=error?'notice error':'notice';el.hidden=false;}
