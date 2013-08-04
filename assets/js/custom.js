

/***************************************************
prettyPhoto
***************************************************/

jQuery(document).ready(function () {
    jQuery("a[rel^='prettyPhoto']").prettyPhoto({ 
	animation_speed: 'normal', 
	theme: 'light_square', 
	slideshow: 3000, 
	autoplay_slideshow: false, 
	social_tools: false 
	});

});

/***************************************************
responsive menu
***************************************************/

jQuery(function (jQuery) {
    jQuery("#main-nav").append("<select/>");
    jQuery("<option />", {
        "selected": "selected",
        "value": "",
        "text": "Choose section"
    }).appendTo("#main-nav select");
    //new dropdown menu
    jQuery("#main-nav a").each(function () {
        var el = jQuery(this);
        var perfix = '';
        switch (el.parents().length) {
            case (11):
                perfix = '-';
                break;
            case (13):
                perfix = '--';
                break;
            default:
                perfix = '';
                break;

        }
        jQuery("<option />", {
            "value": el.attr("href"),
            "text": perfix + el.text()
        }).appendTo("#main-nav select");
    });

    jQuery('#main-nav select').change(function () {

        window.location.href = this.value;

    });
});



