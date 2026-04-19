trigger AccountRating on Account (after update) {
    AccountService.updateRatings(Trigger.new);
}
