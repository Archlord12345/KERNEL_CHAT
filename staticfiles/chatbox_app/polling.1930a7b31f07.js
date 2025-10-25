(function () {
    const POLL_INTERVAL = 5000;

    function schedulePoll(videoId) {
        setTimeout(() => pollVideoStatus(videoId), POLL_INTERVAL);
    }

    function pollVideoStatus(videoId) {
        fetch(`/videos/${videoId}/status/`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.status === "completed" && data.video_url) {
                    window.location.reload();
                } else if (data.status === "failed") {
                    console.error("Génération vidéo échouée", data);
                    window.location.reload();
                } else {
                    schedulePoll(videoId);
                }
            })
            .catch(error => {
                console.error("Erreur de polling", error);
                schedulePoll(videoId);
            });
    }

    const pendingVideos = document.querySelectorAll("[data-video-pending='true']");
    pendingVideos.forEach(node => {
        const videoId = node.dataset.videoId;
        if (videoId) {
            schedulePoll(videoId);
        }
    });
})();
