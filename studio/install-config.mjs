// Only update the checkout path. Existing provider/runtime options belong to the user.
export function configureDesktop(patch,root) {
  const marker=/# BEGIN LinkMind desktop configuration\n([\s\S]*?)# END LinkMind desktop configuration/g;
  let found=false;
  const updated=patch.replace(marker,(block)=>{
    if(found)throw new Error('Multiple LinkMind configuration blocks; resolve them before installing');
    found=true;
    if(!/^  config:\s*$/m.test(block))throw new Error('LinkMind configuration block has no config mapping');
    const line='    root: '+JSON.stringify(root);
    return /^    root:.*$/m.test(block)?block.replace(/^    root:.*$/m,()=>line):block.replace(/^  config:\s*$/m,()=> '  config:\n'+line);
  });
  return found?updated:updated+'\n# BEGIN LinkMind desktop configuration\n- id: linkmind-studio\n  config:\n    root: '+JSON.stringify(root)+'\n# END LinkMind desktop configuration\n';
}
