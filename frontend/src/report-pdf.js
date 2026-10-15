// Render the already-masked report locally; no source code or secrets leave the browser.
export async function downloadReportPdf(element, projectName) {
  if (!element) throw new Error('报告尚未准备好，请稍后再试。');
  const [{ default: html2canvas }, { jsPDF }] = await Promise.all([import('html2canvas'), import('jspdf')]);
  await document.fonts.ready;
  const surface = element.cloneNode(true);
  surface.querySelectorAll('.no-print').forEach(node => node.remove());
  Object.assign(surface.style, { position: 'absolute', left: '-12000px', top: '0', width: '800px', maxWidth: 'none', padding: '28px', margin: '0', background: '#ffffff', boxShadow: 'none', border: '0', borderRadius: '0', animation: 'none', color: '#27354b' });
  surface.classList.add('pdf-export-surface');
  document.body.append(surface);
  try {
    const pdf = new jsPDF({unit:'mm',format:'a4',compress:true});
    const margin=15, width=180, bottom=277;
    let y=margin;
    for (const block of surface.children) {
      const canvas=await html2canvas(block,{scale:2,backgroundColor:'#ffffff',logging:false,windowWidth:1280});
      if (!canvas.width || !canvas.height) continue;
      const mmPerPixel=width/canvas.width;
      const height=canvas.height*mmPerPixel;
      if(y>margin && (height > bottom-y)) { pdf.addPage(); y=margin; }
      // Text line rectangles prevent page boundaries from cutting Chinese text in two.
      const origin=block.getBoundingClientRect(), lines=[];
      const walker=document.createTreeWalker(block,NodeFilter.SHOW_TEXT);
      while(walker.nextNode()) {
        const range=document.createRange();range.selectNodeContents(walker.currentNode);
        for(const rect of range.getClientRects())lines.push({top:(rect.top-origin.top)*2,bottom:(rect.bottom-origin.top)*2});
      }
      let offset=0;
      while(offset<canvas.height) {
        let cut=Math.min(canvas.height,offset+Math.floor((bottom-y)/mmPerPixel));
        for(const line of lines) if(line.top<cut && line.bottom>cut && line.top>offset)cut=Math.min(cut,Math.floor(line.top)-2);
        if(cut<=offset) { pdf.addPage(); y=margin; continue; }
        const segment=document.createElement('canvas');segment.width=canvas.width;segment.height=cut-offset;
        segment.getContext('2d').drawImage(canvas,0,offset,canvas.width,segment.height,0,0,canvas.width,segment.height);
        pdf.addImage(segment.toDataURL('image/png'),'PNG',margin,y,width,segment.height*mmPerPixel,undefined,'FAST');
        y+=segment.height*mmPerPixel;offset=cut;
        if(offset<canvas.height) { pdf.addPage();y=margin; }
      }
      y+=5;
    }
    const pages=pdf.getNumberOfPages();
    for(let i=1;i<=pages;i++){pdf.setPage(i);pdf.setFontSize(9);pdf.setTextColor(90,110,120);pdf.text(`源界  |  ${i} / ${pages}`,195,289,{align:'right'});}
    const name=String(projectName||'源界').replace(/[<>:"/\\|?*\x00-\x1f]/g,'_').slice(0,60);
    pdf.save(`${name}-安全审查报告.pdf`);
  } finally { surface.remove(); }
}
