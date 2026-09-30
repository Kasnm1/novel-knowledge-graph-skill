() => {
          window.addEventListener('hashchange', function(){
            const r = (typeof RT !== 'undefined' && RT) ? RT : (window.__atlasRoute || {});
            if (r.view === 'entity' && r.kind !== 'char'){
              const s = document.getElementById('sec-tags');
              if (s) s.remove();
            }
            if (r.view === 'entity' && r.id === 'char_qin_chao'){
              const c = document.querySelector('#sec-tags .tag-chip');
              if (c && !document.getElementById('leak-probe')){
                const d = document.createElement('div');
                d.id = 'leak-probe';
                d.textContent = c.dataset.tag;
                document.getElementById('page').appendChild(d);
              }
            }
          });
          return { listeners: 'installed', routeExport: typeof window.__atlasRoute };
        }