  Option B: Optimistic WebSocket Updates

  // WebSocket updates UI immediately, REST confirms
  websocket.on('pipeline_completed', (data) => {
    // Update UI optimistically
    updateBatchStatus(data.batch_id, 'completed');
    // Confirm with REST API in background
    verifyWithAPI(data.batch_id);
