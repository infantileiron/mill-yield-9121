export async function api(path,options={}) {
 const token=localStorage.getItem('mill-token');
 const res=await fetch('/api'+path,{...options,headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{}),...options.headers}});
 if(!res.ok){let d=await res.json().catch(()=>({detail:'网络响应异常'})); if(res.status===401&&path!='/auth/login'){localStorage.removeItem('mill-token');location.reload();} throw Error(typeof d.detail==='string'?d.detail:JSON.stringify(d.detail));}
 return res.json();
}
export const post=(path,data)=>api(path,{method:'POST',body:JSON.stringify(data)});
export async function download(id){const r=await fetch(`/api/reviews/${id}/export`,{headers:{Authorization:'Bearer '+localStorage.getItem('mill-token')}});if(!r.ok)throw Error('报告尚不可导出');const a=document.createElement('a');a.href=URL.createObjectURL(await r.blob());a.download=`mill-yield-review-${id}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),5000);}
